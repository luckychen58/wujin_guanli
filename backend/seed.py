from __future__ import annotations

from copy import deepcopy

SEED_CUSTOMERS = [
    {
        "id": "CUS-001",
        "name": "众鑫五金总汇",
        "tier": "A",
        "owner": "陈旭",
        "phone": "13800010001",
        "city": "上海",
        "credit_limit": 80000,
        "payment_term_days": 30,
    },
    {
        "id": "CUS-002",
        "name": "海川装饰工程",
        "tier": "B",
        "owner": "赵峰",
        "phone": "13800010002",
        "city": "苏州",
        "credit_limit": 50000,
        "payment_term_days": 15,
    },
    {
        "id": "CUS-003",
        "name": "城东机电门市",
        "tier": "C",
        "owner": "孙强",
        "phone": "13800010003",
        "city": "嘉兴",
        "credit_limit": 20000,
        "payment_term_days": 7,
    },
    {
        "id": "CUS-004",
        "name": "品创弱电安装队",
        "tier": "B",
        "owner": "林霖",
        "phone": "13800010004",
        "city": "昆山",
        "credit_limit": 35000,
        "payment_term_days": 10,
    },
]

SEED_PRODUCTS = [
    {
        "id": "PRD-001",
        "sku": "JG-M8-80",
        "name": "膨胀螺栓 M8*80",
        "category": "紧固件",
        "brand": "固锋",
        "spec": "M8 x 80",
        "unit": "盒",
        "base_price": 38,
        "on_hand": 140,
        "reserved": 0,
        "reorder_point": 40,
    },
    {
        "id": "PRD-002",
        "sku": "HJ-304-4",
        "name": "304 不锈钢合页 4寸",
        "category": "门窗配件",
        "brand": "海虎机械",
        "spec": "4 寸",
        "unit": "付",
        "base_price": 16,
        "on_hand": 60,
        "reserved": 0,
        "reorder_point": 20,
    },
    {
        "id": "PRD-003",
        "sku": "XC-PVC-2414",
        "name": "PVC 线槽 24x14",
        "category": "电工辅料",
        "brand": "立通",
        "spec": "24 x 14",
        "unit": "根",
        "base_price": 12,
        "on_hand": 90,
        "reserved": 0,
        "reorder_point": 30,
    },
    {
        "id": "PRD-004",
        "sku": "QJ-100-50",
        "name": "热镀锌桥架 100x50",
        "category": "桥架",
        "brand": "盛达",
        "spec": "100 x 50",
        "unit": "节",
        "base_price": 82,
        "on_hand": 8,
        "reserved": 0,
        "reorder_point": 12,
    },
    {
        "id": "PRD-005",
        "sku": "QGP-105",
        "name": "切割片 105mm",
        "category": "工具耗材",
        "brand": "锐切",
        "spec": "105 mm",
        "unit": "盒",
        "base_price": 24,
        "on_hand": 32,
        "reserved": 0,
        "reorder_point": 10,
    },
    {
        "id": "PRD-006",
        "sku": "BXG-6-60",
        "name": "自攻螺丝 6*60",
        "category": "紧固件",
        "brand": "匠拓",
        "spec": "6 x 60",
        "unit": "盒",
        "base_price": 29,
        "on_hand": 44,
        "reserved": 0,
        "reorder_point": 18,
    },
]


def get_seed_customers() -> list[dict[str, object]]:
    return deepcopy(SEED_CUSTOMERS)



def get_seed_products() -> list[dict[str, object]]:
    return deepcopy(SEED_PRODUCTS)

