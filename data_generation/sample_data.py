from __future__ import annotations

from .schemas import SeedBehavior, SeedProduct, SeedUser


SAMPLE_PRODUCTS = [
    SeedProduct(
        product_id="P001",
        title="Sony WH-1000XM5 无线降噪耳机",
        category="耳机",
        price=2499,
        description="头戴式主动降噪耳机，适合通勤、办公、长时间学习和差旅。",
        tag=["降噪", "头戴式", "通勤", "办公"],
        hot_score=96,
        stock=80,
    ),
    SeedProduct(
        product_id="P002",
        title="AirPods Pro 2 主动降噪耳机",
        category="耳机",
        price=1899,
        description="入耳式无线耳机，支持主动降噪和空间音频，适合 iPhone 用户。",
        tag=["入耳式", "降噪", "Apple", "通勤"],
        hot_score=94,
        stock=300,
    ),
    SeedProduct(
        product_id="P003",
        title="Anker 737 大容量充电宝",
        category="配件",
        price=799,
        description="支持多设备快充的大容量移动电源，适合旅行、露营和外出办公。",
        tag=["快充", "旅行", "露营", "大容量"],
        hot_score=88,
        stock=220,
    ),
    SeedProduct(
        product_id="P004",
        title="正浩 RIVER 2 便携户外电源",
        category="户外电源",
        price=1699,
        description="便携储能电源，适合露营、自驾、户外拍摄和应急备用。",
        tag=["露营", "户外", "便携", "应急"],
        hot_score=90,
        stock=70,
    ),
]


SAMPLE_USERS = [
    SeedUser(
        user_id="web_user",
        segments=["active", "commuter"],
        behaviors=[
            SeedBehavior(product_id="P001", behavior_type="view", weight=1.0),
            SeedBehavior(product_id="P002", behavior_type="click", weight=1.5),
            SeedBehavior(product_id="P003", behavior_type="view", weight=0.8),
        ],
    ),
    SeedUser(
        user_id="camp_user",
        segments=["active", "outdoor"],
        behaviors=[
            SeedBehavior(product_id="P004", behavior_type="click", weight=2.0),
            SeedBehavior(product_id="P003", behavior_type="cart", weight=2.5),
        ],
    ),
]
