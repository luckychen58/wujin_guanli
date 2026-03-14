from __future__ import annotations

import sqlite3
from pathlib import Path

from . import auth
from .seed import get_seed_customers, get_seed_products

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "hardware_oms.sqlite3"

DEFAULT_META = {
    "demo_ready": "0",
    "order_seq": "1",
    "receivable_seq": "1",
    "purchase_seq": "1",
    "movement_seq": "1",
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    tier TEXT NOT NULL,
    owner TEXT NOT NULL,
    phone TEXT NOT NULL,
    city TEXT NOT NULL,
    credit_limit REAL NOT NULL,
    payment_term_days INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    sku TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    brand TEXT NOT NULL,
    spec TEXT NOT NULL,
    unit TEXT NOT NULL,
    base_price REAL NOT NULL,
    on_hand INTEGER NOT NULL,
    reserved INTEGER NOT NULL,
    reorder_point INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    happened_at TEXT NOT NULL,
    user_id TEXT,
    username TEXT,
    display_name TEXT,
    role TEXT,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    details_json TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    shipment_status TEXT NOT NULL,
    payment_status TEXT NOT NULL,
    review_flags_json TEXT NOT NULL,
    notes TEXT NOT NULL,
    total_amount REAL NOT NULL,
    FOREIGN KEY(customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS order_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    product_name TEXT NOT NULL,
    sku TEXT NOT NULL,
    spec TEXT NOT NULL,
    unit TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    allocated_qty INTEGER NOT NULL,
    shipped_qty INTEGER NOT NULL,
    shortage_qty INTEGER NOT NULL,
    line_amount REAL NOT NULL,
    FOREIGN KEY(order_id) REFERENCES orders(id),
    FOREIGN KEY(product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS receivables (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    total_amount REAL NOT NULL,
    received_amount REAL NOT NULL,
    due_date TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(order_id) REFERENCES orders(id),
    FOREIGN KEY(customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS purchase_tasks (
    id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    shortage_qty INTEGER NOT NULL,
    recommended_qty INTEGER NOT NULL,
    received_qty INTEGER NOT NULL,
    linked_order_ids_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS inventory_movements (
    id TEXT PRIMARY KEY,
    happened_at TEXT NOT NULL,
    product_id TEXT NOT NULL,
    product_name TEXT NOT NULL,
    type TEXT NOT NULL,
    quantity REAL NOT NULL,
    reference_id TEXT NOT NULL,
    note TEXT NOT NULL
);
"""


BUSINESS_TABLES = [
    "inventory_movements",
    "order_lines",
    "receivables",
    "purchase_tasks",
    "orders",
    "customers",
    "products",
]



def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection



def ensure_meta_defaults(connection: sqlite3.Connection) -> None:
    for key, value in DEFAULT_META.items():
        connection.execute(
            "INSERT OR IGNORE INTO app_meta(key, value) VALUES(?, ?)",
            (key, value),
        )



def reset_business_meta(connection: sqlite3.Connection) -> None:
    for key, value in DEFAULT_META.items():
        connection.execute(
            "INSERT OR REPLACE INTO app_meta(key, value) VALUES(?, ?)",
            (key, value),
        )



def seed_reference_data(connection: sqlite3.Connection) -> None:
    customer_count = connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    product_count = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]

    if customer_count == 0:
        connection.executemany(
            """
            INSERT INTO customers(
                id, name, tier, owner, phone, city, credit_limit, payment_term_days
            ) VALUES(:id, :name, :tier, :owner, :phone, :city, :credit_limit, :payment_term_days)
            """,
            get_seed_customers(),
        )

    if product_count == 0:
        connection.executemany(
            """
            INSERT INTO products(
                id, sku, name, category, brand, spec, unit, base_price, on_hand, reserved, reorder_point
            ) VALUES(:id, :sku, :name, :category, :brand, :spec, :unit, :base_price, :on_hand, :reserved, :reorder_point)
            """,
            get_seed_products(),
        )



def initialize_database() -> None:
    with get_connection() as connection:
        connection.executescript(SCHEMA_SQL)
        ensure_meta_defaults(connection)
        seed_reference_data(connection)
        auth.ensure_seed_users(connection)



def reset_database(connection: sqlite3.Connection) -> None:
    for table_name in BUSINESS_TABLES:
        connection.execute(f"DELETE FROM {table_name}")
    reset_business_meta(connection)
    seed_reference_data(connection)
    auth.ensure_seed_users(connection)
