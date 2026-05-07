from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import init_db
from database.models import InventoryRecord, ProductRecord, UserBehaviorRecord, UserRecord
from database.session import ProductSessionLocal, UserSessionLocal


PRODUCTS = [
    {
        "product_id": "P001",
        "name": "Bose QuietComfort Ultra 消噪耳机",
        "category": "耳机",
        "price": 2999,
        "description": "头戴式无线蓝牙耳机，主动降噪，适合通勤、办公和长途旅行。",
        "brand": "Bose",
        "seller_id": "S001",
        "tags": ["降噪", "头戴式", "通勤", "蓝牙"],
        "hot_score": 98,
        "stock": 120,
    },
    {
        "product_id": "P002",
        "name": "Sony WH-1000XM5 无线降噪耳机",
        "category": "耳机",
        "price": 2499,
        "description": "轻量化头戴耳机，降噪和人声通话表现稳定，适合办公学习。",
        "brand": "Sony",
        "seller_id": "S002",
        "tags": ["降噪", "办公", "头戴式", "长续航"],
        "hot_score": 95,
        "stock": 80,
    },
    {
        "product_id": "P003",
        "name": "AirPods Pro 2 主动降噪耳机",
        "category": "耳机",
        "price": 1899,
        "description": "入耳式无线耳机，主动降噪，空间音频，适合 iPhone 用户日常通勤。",
        "brand": "Apple",
        "seller_id": "S003",
        "tags": ["入耳式", "降噪", "Apple", "通勤"],
        "hot_score": 92,
        "stock": 300,
    },
    {
        "product_id": "P004",
        "name": "小米 Buds 5 Pro",
        "category": "耳机",
        "price": 699,
        "description": "真无线蓝牙耳机，性价比高，适合学生和日常听歌。",
        "brand": "小米",
        "seller_id": "S004",
        "tags": ["性价比", "真无线", "学生", "蓝牙"],
        "hot_score": 88,
        "stock": 500,
    },
    {
        "product_id": "P005",
        "name": "iPhone 16 Pro",
        "category": "手机",
        "price": 7999,
        "description": "旗舰智能手机，影像能力强，性能适合游戏、摄影和日常办公。",
        "brand": "Apple",
        "seller_id": "S003",
        "tags": ["旗舰", "拍照", "游戏", "新品"],
        "hot_score": 99,
        "stock": 60,
    },
    {
        "product_id": "P006",
        "name": "华为 Mate 70 Pro",
        "category": "手机",
        "price": 6999,
        "description": "高端旗舰手机，适合商务、拍照和长续航需求。",
        "brand": "华为",
        "seller_id": "S005",
        "tags": ["旗舰", "商务", "长续航", "拍照"],
        "hot_score": 96,
        "stock": 90,
    },
    {
        "product_id": "P007",
        "name": "Anker 737 充电宝",
        "category": "配件",
        "price": 799,
        "description": "大容量移动电源，支持快充，适合旅行、露营和多设备充电。",
        "brand": "Anker",
        "seller_id": "S006",
        "tags": ["快充", "旅行", "露营", "大容量"],
        "hot_score": 87,
        "stock": 260,
    },
    {
        "product_id": "P008",
        "name": "正浩 RIVER 2 户外电源",
        "category": "户外电源",
        "price": 1699,
        "description": "便携储能电源，适合露营、自驾、户外拍摄和应急备用。",
        "brand": "EcoFlow",
        "seller_id": "S007",
        "tags": ["露营", "户外", "便携", "应急"],
        "hot_score": 90,
        "stock": 70,
    },
    {
        "product_id": "P009",
        "name": "迪卡侬双人自动帐篷",
        "category": "户外",
        "price": 599,
        "description": "轻量自动帐篷，适合周末露营、公园休闲和短途户外活动。",
        "brand": "迪卡侬",
        "seller_id": "S008",
        "tags": ["露营", "帐篷", "轻量", "户外"],
        "hot_score": 84,
        "stock": 150,
    },
    {
        "product_id": "P010",
        "name": "戴森 Supersonic 吹风机",
        "category": "个护",
        "price": 2990,
        "description": "高速吹风机，控温护发，适合日常造型和减少毛躁。",
        "brand": "Dyson",
        "seller_id": "S009",
        "tags": ["护发", "高速", "造型", "礼物"],
        "hot_score": 83,
        "stock": 45,
    },
]


def seed_products_and_inventory() -> None:
    with ProductSessionLocal() as session:
        for item in PRODUCTS:
            product = session.get(ProductRecord, item["product_id"])
            if not product:
                product = ProductRecord(product_id=item["product_id"])
                session.add(product)

            product.name = item["name"]
            product.category = item["category"]
            product.price = float(item["price"])
            product.description = item["description"]
            product.brand = item["brand"]
            product.seller_id = item["seller_id"]
            product.tags_json = json.dumps(item["tags"], ensure_ascii=False)
            product.image_url = ""
            product.status = "active"
            product.hot_score = float(item["hot_score"])

            inventory = session.get(InventoryRecord, item["product_id"])
            if not inventory:
                inventory = InventoryRecord(product_id=item["product_id"])
                session.add(inventory)
            inventory.stock = int(item["stock"])
            inventory.reserved_stock = 0

        session.commit()


def seed_user_history() -> None:
    now = datetime.utcnow()
    with UserSessionLocal() as session:
        user = session.get(UserRecord, "web_user")
        if not user:
            user = UserRecord(user_id="web_user")
            session.add(user)
        user.segments_json = json.dumps(["active"], ensure_ascii=False)
        user.preferred_categories_json = json.dumps(["耳机", "配件"], ensure_ascii=False)

        existing_count = session.query(UserBehaviorRecord).filter_by(user_id="web_user").count()
        if existing_count == 0:
            interactions = [
                ("P001", "view", 1.0),
                ("P002", "click", 1.5),
                ("P003", "view", 1.0),
                ("P007", "click", 1.2),
            ]
            for offset, (product_id, behavior_type, weight) in enumerate(interactions):
                session.add(
                    UserBehaviorRecord(
                        user_id="web_user",
                        product_id=product_id,
                        behavior_type=behavior_type,
                        scene="demo_seed",
                        weight=weight,
                        created_at=now - timedelta(hours=offset),
                    )
                )

        session.commit()


def main() -> None:
    init_db()
    seed_products_and_inventory()
    seed_user_history()
    print(f"Seeded {len(PRODUCTS)} products, inventory rows, and web_user behavior history.")


if __name__ == "__main__":
    main()
