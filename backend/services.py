from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

PRICE_MULTIPLIER = {
    "A": 0.92,
    "B": 0.96,
    "C": 1.0,
}



def round_currency(value: float) -> float:
    return round(value + 1e-9, 2)



def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def shift_days(base_date: str, days: int) -> str:
    return (datetime.fromisoformat(base_date) + timedelta(days=days)).isoformat()



def to_date_input(date_string: str) -> str:
    return datetime.fromisoformat(date_string).date().isoformat()



def next_id(connection: sqlite3.Connection, meta_key: str, prefix: str) -> str:
    row = connection.execute(
        "SELECT value FROM app_meta WHERE key = ?",
        (meta_key,),
    ).fetchone()
    current = int(row["value"] if row else 1)
    connection.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES(?, ?)",
        (meta_key, str(current + 1)),
    )
    return f"{prefix}-{current:04d}"



def get_customer_outstanding(connection: sqlite3.Connection, customer_id: str) -> float:
    row = connection.execute(
        """
        SELECT COALESCE(SUM(total_amount - received_amount), 0) AS outstanding
        FROM receivables
        WHERE customer_id = ?
        """,
        (customer_id,),
    ).fetchone()
    return round_currency(float(row["outstanding"]))



def derive_receivable_status(receivable: dict[str, Any]) -> str:
    outstanding = float(receivable["totalAmount"]) - float(receivable["receivedAmount"])
    if outstanding <= 0:
        return "已收清"
    if float(receivable["receivedAmount"]) > 0:
        return "部分收款"
    if datetime.fromisoformat(receivable["dueDate"]) < datetime.now(timezone.utc):
        return "已逾期"
    return "未收款"



def derive_shipment_status(lines: list[dict[str, Any]]) -> str:
    ordered_qty = sum(int(line["quantity"]) for line in lines)
    shipped_qty = sum(int(line["shippedQty"]) for line in lines)
    if shipped_qty <= 0:
        return "未发货"
    if shipped_qty < ordered_qty:
        return "部分发货"
    return "已发货"



def derive_order_status(lines: list[dict[str, Any]], payment_status: str) -> str:
    ordered_qty = sum(int(line["quantity"]) for line in lines)
    shipped_qty = sum(int(line["shippedQty"]) for line in lines)
    shortage_qty = sum(int(line["shortageQty"]) for line in lines)
    shippable_qty = sum(max(int(line["allocatedQty"]) - int(line["shippedQty"]), 0) for line in lines)

    if shipped_qty >= ordered_qty and payment_status == "已收清":
        return "已闭环"
    if shipped_qty >= ordered_qty:
        return "已发货待回款"
    if shipped_qty > 0 and shortage_qty > 0:
        return "部分发货待补货"
    if shipped_qty > 0:
        return "部分发货"
    if shortage_qty > 0 and shippable_qty > 0:
        return "部分备货待采购"
    if shortage_qty > 0:
        return "待采购"
    if shippable_qty > 0:
        return "待出库"
    return "新建"



def get_unit_price(customer_tier: str, base_price: float) -> float:
    return round_currency(float(base_price) * PRICE_MULTIPLIER.get(customer_tier, 1.0))



def log_inventory_movement(
    connection: sqlite3.Connection,
    *,
    product_id: str,
    product_name: str,
    movement_type: str,
    quantity: float,
    reference_id: str,
    note: str,
) -> None:
    connection.execute(
        """
        INSERT INTO inventory_movements(id, happened_at, product_id, product_name, type, quantity, reference_id, note)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            next_id(connection, "movement_seq", "MOV"),
            utc_now_iso(),
            product_id,
            product_name,
            movement_type,
            quantity,
            reference_id,
            note,
        ),
    )



def fetch_receivable_by_order(connection: sqlite3.Connection, order_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM receivables WHERE order_id = ?",
        (order_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "orderId": row["order_id"],
        "customerId": row["customer_id"],
        "totalAmount": float(row["total_amount"]),
        "receivedAmount": float(row["received_amount"]),
        "dueDate": row["due_date"],
        "status": row["status"],
        "createdAt": row["created_at"],
    }



def fetch_order_lines(connection: sqlite3.Connection, order_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM order_lines WHERE order_id = ? ORDER BY id ASC",
        (order_id,),
    ).fetchall()
    return [
        {
            "productId": row["product_id"],
            "productName": row["product_name"],
            "sku": row["sku"],
            "spec": row["spec"],
            "unit": row["unit"],
            "quantity": int(row["quantity"]),
            "unitPrice": float(row["unit_price"]),
            "allocatedQty": int(row["allocated_qty"]),
            "shippedQty": int(row["shipped_qty"]),
            "shortageQty": int(row["shortage_qty"]),
            "lineAmount": float(row["line_amount"]),
        }
        for row in rows
    ]



def refresh_order(connection: sqlite3.Connection, order_id: str) -> None:
    lines = fetch_order_lines(connection, order_id)
    receivable = fetch_receivable_by_order(connection, order_id)
    payment_status = receivable["status"] if receivable else "未收款"
    if receivable:
        payment_status = derive_receivable_status(receivable)
        connection.execute(
            "UPDATE receivables SET status = ? WHERE id = ?",
            (payment_status, receivable["id"]),
        )
    shipment_status = derive_shipment_status(lines)
    order_status = derive_order_status(lines, payment_status)
    connection.execute(
        "UPDATE orders SET status = ?, shipment_status = ?, payment_status = ? WHERE id = ?",
        (order_status, shipment_status, payment_status, order_id),
    )



def ensure_purchase_task(
    connection: sqlite3.Connection,
    *,
    product_row: sqlite3.Row,
    shortage_qty: int,
    order_id: str,
) -> None:
    pending_task = connection.execute(
        "SELECT * FROM purchase_tasks WHERE product_id = ? AND status != '已完成' LIMIT 1",
        (product_row["id"],),
    ).fetchone()
    inventory_gap = max(int(product_row["reorder_point"]) - (int(product_row["on_hand"]) - int(product_row["reserved"])), 0)
    recommended_qty = shortage_qty + inventory_gap

    if pending_task:
        linked_order_ids = json.loads(pending_task["linked_order_ids_json"])
        if order_id not in linked_order_ids:
            linked_order_ids.append(order_id)
        shortage_total = int(pending_task["shortage_qty"]) + shortage_qty
        connection.execute(
            """
            UPDATE purchase_tasks
            SET shortage_qty = ?, recommended_qty = ?, linked_order_ids_json = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                shortage_total,
                max(int(pending_task["recommended_qty"]), shortage_total + inventory_gap),
                json.dumps(linked_order_ids, ensure_ascii=False),
                "部分入库待补齐" if int(pending_task["received_qty"]) > 0 else "待采购",
                utc_now_iso(),
                pending_task["id"],
            ),
        )
        return

    connection.execute(
        """
        INSERT INTO purchase_tasks(
            id, product_id, shortage_qty, recommended_qty, received_qty, linked_order_ids_json, status, created_at, updated_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            next_id(connection, "purchase_seq", "PUR"),
            product_row["id"],
            shortage_qty,
            recommended_qty,
            0,
            json.dumps([order_id], ensure_ascii=False),
            "待采购",
            utc_now_iso(),
            utc_now_iso(),
        ),
    )



def recompute_purchase_task(connection: sqlite3.Connection, product_id: str) -> None:
    task = connection.execute(
        "SELECT * FROM purchase_tasks WHERE product_id = ? AND status != '已完成' LIMIT 1",
        (product_id,),
    ).fetchone()
    if not task:
        return

    outstanding_shortage = connection.execute(
        "SELECT COALESCE(SUM(shortage_qty), 0) AS shortage FROM order_lines WHERE product_id = ?",
        (product_id,),
    ).fetchone()["shortage"]
    product = connection.execute(
        "SELECT * FROM products WHERE id = ?",
        (product_id,),
    ).fetchone()
    recommended_qty = int(outstanding_shortage) + max(
        int(product["reorder_point"]) - (int(product["on_hand"]) - int(product["reserved"])),
        0,
    )
    status = "已完成"
    if int(outstanding_shortage) > 0:
        status = "部分入库待补齐" if int(task["received_qty"]) > 0 else "待采购"

    connection.execute(
        """
        UPDATE purchase_tasks
        SET shortage_qty = ?, recommended_qty = ?, status = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            int(outstanding_shortage),
            0 if int(outstanding_shortage) <= 0 else recommended_qty,
            status,
            utc_now_iso(),
            task["id"],
        ),
    )



def allocate_replenished_stock(connection: sqlite3.Connection, product_id: str) -> None:
    product = connection.execute(
        "SELECT * FROM products WHERE id = ?",
        (product_id,),
    ).fetchone()
    if not product:
        return

    available = int(product["on_hand"]) - int(product["reserved"])
    waiting_lines = connection.execute(
        """
        SELECT order_lines.id AS line_id, order_lines.shortage_qty, orders.id AS order_id
        FROM order_lines
        INNER JOIN orders ON orders.id = order_lines.order_id
        WHERE order_lines.product_id = ? AND order_lines.shortage_qty > 0
        ORDER BY orders.created_at ASC, order_lines.id ASC
        """,
        (product_id,),
    ).fetchall()

    affected_orders: set[str] = set()
    for line in waiting_lines:
        if available <= 0:
            break
        shortage_qty = int(line["shortage_qty"])
        allocated = min(available, shortage_qty)
        if allocated <= 0:
            continue

        connection.execute(
            "UPDATE order_lines SET allocated_qty = allocated_qty + ?, shortage_qty = shortage_qty - ? WHERE id = ?",
            (allocated, allocated, line["line_id"]),
        )
        connection.execute(
            "UPDATE products SET reserved = reserved + ? WHERE id = ?",
            (allocated, product_id),
        )
        available -= allocated
        affected_orders.add(line["order_id"])

        log_inventory_movement(
            connection,
            product_id=product_id,
            product_name=product["name"],
            movement_type="补货锁库",
            quantity=allocated,
            reference_id=line["order_id"],
            note=f"采购到货后为订单 {line['order_id']} 重新锁库",
        )

    for order_id in affected_orders:
        refresh_order(connection, order_id)



def create_order(connection: sqlite3.Connection, payload: dict[str, Any]) -> str:
    customer_id = str(payload.get("customerId") or "")
    customer = connection.execute(
        "SELECT * FROM customers WHERE id = ?",
        (customer_id,),
    ).fetchone()
    if not customer:
        raise ValueError("请选择客户后再创建订单。")

    line_inputs = payload.get("lines") or []
    if not isinstance(line_inputs, list) or not line_inputs:
        raise ValueError("请至少选择一个商品。")

    order_id = next_id(connection, "order_seq", "SO")
    receivable_id = next_id(connection, "receivable_seq", "AR")
    created_at = utc_now_iso()
    total_amount = 0.0
    review_flags: list[str] = []
    has_shortage = False
    order_lines: list[dict[str, Any]] = []

    for line_input in line_inputs:
        product_id = str(line_input.get("productId") or "")
        quantity = int(line_input.get("quantity") or 0)
        product = connection.execute(
            "SELECT * FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()
        if not product or quantity <= 0:
            raise ValueError("订单明细里有无效商品或数量。")

        available = int(product["on_hand"]) - int(product["reserved"])
        allocated_qty = min(quantity, available)
        shortage_qty = quantity - allocated_qty
        unit_price = get_unit_price(str(customer["tier"]), float(product["base_price"]))
        line_amount = round_currency(unit_price * quantity)
        total_amount += line_amount

        if allocated_qty > 0:
            connection.execute(
                "UPDATE products SET reserved = reserved + ? WHERE id = ?",
                (allocated_qty, product_id),
            )
            log_inventory_movement(
                connection,
                product_id=product_id,
                product_name=product["name"],
                movement_type="锁库",
                quantity=allocated_qty,
                reference_id=order_id,
                note=f"为订单 {order_id} 锁定库存",
            )

        if shortage_qty > 0:
            has_shortage = True
            ensure_purchase_task(
                connection,
                product_row=product,
                shortage_qty=shortage_qty,
                order_id=order_id,
            )

        order_lines.append(
            {
                "productId": product_id,
                "productName": product["name"],
                "sku": product["sku"],
                "spec": product["spec"],
                "unit": product["unit"],
                "quantity": quantity,
                "unitPrice": unit_price,
                "allocatedQty": allocated_qty,
                "shippedQty": 0,
                "shortageQty": shortage_qty,
                "lineAmount": line_amount,
            }
        )

    total_amount = round_currency(total_amount)
    projected_exposure = get_customer_outstanding(connection, customer_id) + total_amount
    if projected_exposure > float(customer["credit_limit"]):
        review_flags.append("超信用额度")
    if has_shortage:
        review_flags.append("存在欠货")

    due_date = shift_days(created_at, int(customer["payment_term_days"]))
    receivable = {
        "id": receivable_id,
        "orderId": order_id,
        "customerId": customer_id,
        "totalAmount": total_amount,
        "receivedAmount": 0.0,
        "dueDate": due_date,
        "status": "未收款",
        "createdAt": created_at,
    }
    payment_status = derive_receivable_status(receivable)
    shipment_status = derive_shipment_status(order_lines)
    order_status = derive_order_status(order_lines, payment_status)

    connection.execute(
        """
        INSERT INTO orders(
            id, customer_id, customer_name, created_at, status, shipment_status, payment_status, review_flags_json, notes, total_amount
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            order_id,
            customer_id,
            customer["name"],
            created_at,
            order_status,
            shipment_status,
            payment_status,
            json.dumps(review_flags, ensure_ascii=False),
            str(payload.get("notes") or "").strip(),
            total_amount,
        ),
    )

    connection.executemany(
        """
        INSERT INTO order_lines(
            order_id, product_id, product_name, sku, spec, unit, quantity, unit_price, allocated_qty, shipped_qty, shortage_qty, line_amount
        ) VALUES(:orderId, :productId, :productName, :sku, :spec, :unit, :quantity, :unitPrice, :allocatedQty, :shippedQty, :shortageQty, :lineAmount)
        """,
        [
            {
                "orderId": order_id,
                **line,
            }
            for line in order_lines
        ],
    )

    connection.execute(
        """
        INSERT INTO receivables(id, order_id, customer_id, total_amount, received_amount, due_date, status, created_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            receivable_id,
            order_id,
            customer_id,
            total_amount,
            0.0,
            due_date,
            payment_status,
            created_at,
        ),
    )
    return order_id



def ship_allocated_stock(connection: sqlite3.Connection, order_id: str) -> None:
    order = connection.execute(
        "SELECT id FROM orders WHERE id = ?",
        (order_id,),
    ).fetchone()
    if not order:
        raise ValueError("未找到对应订单。")

    line_rows = connection.execute(
        "SELECT id, product_id, product_name, allocated_qty, shipped_qty FROM order_lines WHERE order_id = ?",
        (order_id,),
    ).fetchall()

    for line in line_rows:
        pending_shipment = max(int(line["allocated_qty"]) - int(line["shipped_qty"]), 0)
        if pending_shipment <= 0:
            continue
        connection.execute(
            "UPDATE products SET on_hand = on_hand - ?, reserved = reserved - ? WHERE id = ?",
            (pending_shipment, pending_shipment, line["product_id"]),
        )
        connection.execute(
            "UPDATE order_lines SET shipped_qty = shipped_qty + ? WHERE id = ?",
            (pending_shipment, line["id"]),
        )
        log_inventory_movement(
            connection,
            product_id=line["product_id"],
            product_name=line["product_name"],
            movement_type="出库",
            quantity=pending_shipment,
            reference_id=order_id,
            note=f"订单 {order_id} 已执行出库",
        )

    refresh_order(connection, order_id)



def collect_payment(connection: sqlite3.Connection, receivable_id: str, amount: float) -> None:
    if amount <= 0:
        raise ValueError("收款金额必须大于 0。")

    receivable_row = connection.execute(
        "SELECT * FROM receivables WHERE id = ?",
        (receivable_id,),
    ).fetchone()
    if not receivable_row:
        raise ValueError("未找到应收记录。")

    before_amount = float(receivable_row["received_amount"])
    next_amount = round_currency(min(float(receivable_row["total_amount"]), before_amount + amount))
    applied_amount = round_currency(next_amount - before_amount)
    receivable = {
        "id": receivable_row["id"],
        "orderId": receivable_row["order_id"],
        "customerId": receivable_row["customer_id"],
        "totalAmount": float(receivable_row["total_amount"]),
        "receivedAmount": next_amount,
        "dueDate": receivable_row["due_date"],
        "status": receivable_row["status"],
        "createdAt": receivable_row["created_at"],
    }
    status = derive_receivable_status(receivable)
    connection.execute(
        "UPDATE receivables SET received_amount = ?, status = ? WHERE id = ?",
        (next_amount, status, receivable_id),
    )
    refresh_order(connection, receivable_row["order_id"])
    log_inventory_movement(
        connection,
        product_id="-",
        product_name=receivable_row["order_id"],
        movement_type="回款",
        quantity=applied_amount,
        reference_id=receivable_id,
        note=f"订单 {receivable_row['order_id']} 登记回款",
    )



def receive_purchase(connection: sqlite3.Connection, task_id: str, quantity: int) -> None:
    if quantity <= 0:
        raise ValueError("入库数量必须大于 0。")

    task = connection.execute(
        "SELECT * FROM purchase_tasks WHERE id = ?",
        (task_id,),
    ).fetchone()
    if not task:
        raise ValueError("未找到采购任务。")

    product = connection.execute(
        "SELECT * FROM products WHERE id = ?",
        (task["product_id"],),
    ).fetchone()
    if not product:
        raise ValueError("未找到采购商品。")

    connection.execute(
        "UPDATE products SET on_hand = on_hand + ? WHERE id = ?",
        (quantity, task["product_id"]),
    )
    connection.execute(
        "UPDATE purchase_tasks SET received_qty = received_qty + ?, updated_at = ? WHERE id = ?",
        (quantity, utc_now_iso(), task_id),
    )
    log_inventory_movement(
        connection,
        product_id=task["product_id"],
        product_name=product["name"],
        movement_type="采购入库",
        quantity=quantity,
        reference_id=task_id,
        note=f"采购任务 {task_id} 已到货入库",
    )
    allocate_replenished_stock(connection, task["product_id"])
    recompute_purchase_task(connection, task["product_id"])



def row_to_customer(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "tier": row["tier"],
        "owner": row["owner"],
        "phone": row["phone"],
        "city": row["city"],
        "creditLimit": float(row["credit_limit"]),
        "paymentTermDays": int(row["payment_term_days"]),
    }



def row_to_product(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "sku": row["sku"],
        "name": row["name"],
        "category": row["category"],
        "brand": row["brand"],
        "spec": row["spec"],
        "unit": row["unit"],
        "basePrice": float(row["base_price"]),
        "stock": {
            "onHand": int(row["on_hand"]),
            "reserved": int(row["reserved"]),
            "reorderPoint": int(row["reorder_point"]),
        },
    }



def build_view_model(connection: sqlite3.Connection) -> dict[str, Any]:
    customers = [
        row_to_customer(row)
        for row in connection.execute("SELECT * FROM customers ORDER BY id ASC").fetchall()
    ]
    products = [
        row_to_product(row)
        for row in connection.execute("SELECT * FROM products ORDER BY id ASC").fetchall()
    ]

    order_rows = connection.execute(
        "SELECT * FROM orders ORDER BY created_at DESC, id DESC"
    ).fetchall()
    line_rows = connection.execute(
        "SELECT * FROM order_lines ORDER BY order_id DESC, id ASC"
    ).fetchall()
    receivable_rows = connection.execute(
        "SELECT * FROM receivables ORDER BY due_date ASC, id ASC"
    ).fetchall()
    purchase_rows = connection.execute(
        "SELECT * FROM purchase_tasks ORDER BY updated_at DESC, id DESC"
    ).fetchall()
    movement_rows = connection.execute(
        "SELECT * FROM inventory_movements ORDER BY happened_at DESC, id DESC LIMIT 8"
    ).fetchall()

    lines_by_order: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in line_rows:
        lines_by_order[row["order_id"]].append(
            {
                "productId": row["product_id"],
                "productName": row["product_name"],
                "sku": row["sku"],
                "spec": row["spec"],
                "unit": row["unit"],
                "quantity": int(row["quantity"]),
                "unitPrice": float(row["unit_price"]),
                "allocatedQty": int(row["allocated_qty"]),
                "shippedQty": int(row["shipped_qty"]),
                "shortageQty": int(row["shortage_qty"]),
                "lineAmount": float(row["line_amount"]),
            }
        )

    receivable_by_order = {}
    receivables = []
    customer_map = {customer["id"]: customer for customer in customers}
    for row in receivable_rows:
        receivable = {
            "id": row["id"],
            "orderId": row["order_id"],
            "customerId": row["customer_id"],
            "customer": customer_map.get(row["customer_id"]),
            "totalAmount": float(row["total_amount"]),
            "receivedAmount": float(row["received_amount"]),
            "dueDate": row["due_date"],
            "status": row["status"],
            "createdAt": row["created_at"],
        }
        receivable["outstandingAmount"] = round_currency(
            receivable["totalAmount"] - receivable["receivedAmount"]
        )
        receivables.append(receivable)
        receivable_by_order[receivable["orderId"]] = receivable

    orders = []
    order_map = {}
    for row in order_rows:
        lines = lines_by_order[row["id"]]
        ordered_qty = sum(line["quantity"] for line in lines)
        allocated_qty = sum(line["allocatedQty"] for line in lines)
        shipped_qty = sum(line["shippedQty"] for line in lines)
        shortage_qty = sum(line["shortageQty"] for line in lines)
        receivable = receivable_by_order.get(row["id"])
        order = {
            "id": row["id"],
            "customerId": row["customer_id"],
            "customerName": row["customer_name"],
            "createdAt": row["created_at"],
            "status": row["status"],
            "shipmentStatus": row["shipment_status"],
            "paymentStatus": row["payment_status"],
            "reviewFlags": json.loads(row["review_flags_json"]),
            "notes": row["notes"],
            "totalAmount": float(row["total_amount"]),
            "lines": lines,
            "orderedQty": ordered_qty,
            "allocatedQty": allocated_qty,
            "shippedQty": shipped_qty,
            "shortageQty": shortage_qty,
            "shippableQty": max(allocated_qty - shipped_qty, 0),
            "receivable": receivable,
            "outstandingAmount": receivable["outstandingAmount"] if receivable else 0,
        }
        orders.append(order)
        order_map[order["id"]] = order

    inventory = []
    for product in products:
        available = product["stock"]["onHand"] - product["stock"]["reserved"]
        health = "健康"
        if available <= 0:
            health = "已断货"
        elif available <= product["stock"]["reorderPoint"]:
            health = "低于安全库存"
        inventory.append({**product, "available": available, "health": health})
    inventory.sort(key=lambda item: item["available"])

    purchase_tasks = []
    for row in purchase_rows:
        linked_order_ids = json.loads(row["linked_order_ids_json"])
        purchase_tasks.append(
            {
                "id": row["id"],
                "productId": row["product_id"],
                "shortageQty": int(row["shortage_qty"]),
                "recommendedQty": int(row["recommended_qty"]),
                "receivedQty": int(row["received_qty"]),
                "status": row["status"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
                "product": next((product for product in products if product["id"] == row["product_id"]), None),
                "linkedOrders": [order_map[order_id] for order_id in linked_order_ids if order_id in order_map],
            }
        )

    outstanding_receivables = round_currency(
        sum(receivable["outstandingAmount"] for receivable in receivables)
    )
    total_sales = round_currency(sum(order["totalAmount"] for order in orders))
    low_stock_count = sum(1 for item in inventory if item["health"] != "健康")
    shortage_orders = sum(1 for order in orders if order["shortageQty"] > 0)
    ready_to_ship = sum(1 for order in orders if order["shippableQty"] > 0)

    top_customers = []
    for customer in customers:
        order_amount = round_currency(
            sum(order["totalAmount"] for order in orders if order["customerId"] == customer["id"])
        )
        top_customers.append(
            {
                **customer,
                "orderAmount": order_amount,
                "outstandingAmount": get_customer_outstanding(connection, customer["id"]),
            }
        )
    top_customers.sort(key=lambda item: item["orderAmount"], reverse=True)
    top_customers = top_customers[:4]

    activity_feed = [
        {
            "id": row["id"],
            "happenedAt": row["happened_at"],
            "productId": row["product_id"],
            "productName": row["product_name"],
            "type": row["type"],
            "quantity": row["quantity"],
            "referenceId": row["reference_id"],
            "note": row["note"],
        }
        for row in movement_rows
    ]

    return {
        "now": datetime.now().date().isoformat(),
        "customers": customers,
        "products": products,
        "orders": orders,
        "receivables": receivables,
        "purchaseTasks": purchase_tasks,
        "inventory": inventory,
        "topCustomers": top_customers,
        "activityFeed": activity_feed,
        "dashboard": {
            "activeOrders": sum(1 for order in orders if order["status"] != "已闭环"),
            "readyToShip": ready_to_ship,
            "shortageOrders": shortage_orders,
            "outstandingReceivables": outstanding_receivables,
            "totalSales": total_sales,
            "lowStockCount": low_stock_count,
        },
    }



def ensure_demo_data(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT value FROM app_meta WHERE key = 'demo_ready'"
    ).fetchone()
    if row and row["value"] == "1":
        return

    order_one = create_order(
        connection,
        {
            "customerId": "CUS-001",
            "lines": [
                {"productId": "PRD-001", "quantity": 90},
                {"productId": "PRD-004", "quantity": 12},
            ],
            "notes": "酒店机电项目首批到货，桥架允许补发。",
        },
    )
    ship_allocated_stock(connection, order_one)

    order_two = create_order(
        connection,
        {
            "customerId": "CUS-002",
            "lines": [
                {"productId": "PRD-002", "quantity": 24},
                {"productId": "PRD-005", "quantity": 18},
            ],
            "notes": "门店促销备货单。",
        },
    )
    ship_allocated_stock(connection, order_two)

    second_receivable = connection.execute(
        "SELECT id FROM receivables WHERE order_id = ?",
        (order_two,),
    ).fetchone()
    if second_receivable:
        collect_payment(connection, second_receivable["id"], 420)

    connection.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES('demo_ready', '1')"
    )

