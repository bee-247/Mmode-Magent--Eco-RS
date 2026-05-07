from __future__ import annotations

import json
from pathlib import Path

from database.models import InventoryRecord, ProductRecord, UserBehaviorRecord, UserRecord
from database.session import ProductSessionLocal, UserSessionLocal


OUTPUT_PATH = Path(__file__).with_name("generated_data.json")


def load_products() -> list[dict]:
    with ProductSessionLocal() as session:
        products = session.query(ProductRecord).order_by(ProductRecord.product_id).all()
        result = []
        for product in products:
            inventory = session.get(InventoryRecord, product.product_id)
            result.append(
                {
                    "product_id": product.product_id,
                    "title": product.name,
                    "category": product.category,
                    "price": product.price,
                    "description": product.description,
                    "tag": parse_json(product.tags_json, []),
                    "hot_score": product.hot_score,
                    "stock": inventory.stock if inventory else 0,
                    "reserved_stock": inventory.reserved_stock if inventory else 0,
                }
            )
        return result


def load_users() -> list[dict]:
    with UserSessionLocal() as session:
        users = session.query(UserRecord).order_by(UserRecord.user_id).all()
        result = []
        for user in users:
            behaviors = (
                session.query(UserBehaviorRecord)
                .filter(UserBehaviorRecord.user_id == user.user_id)
                .order_by(UserBehaviorRecord.created_at.desc())
                .all()
            )
            result.append(
                {
                    "user_id": user.user_id,
                    "segments": parse_json(user.segments_json, []),
                    "preferred_categories": parse_json(
                        user.preferred_categories_json, []
                    ),
                    "behaviors": [
                        {
                            "product_id": behavior.product_id,
                            "behavior_type": behavior.behavior_type,
                            "weight": behavior.weight,
                            "scene": behavior.scene,
                            "created_at": behavior.created_at.isoformat()
                            if behavior.created_at
                            else None,
                        }
                        for behavior in behaviors
                    ],
                }
            )
        return result


def parse_json(raw: str, default):
    try:
        return json.loads(raw or "")
    except json.JSONDecodeError:
        return default


def main() -> None:
    data = {
        "products": load_products(),
        "users": load_users(),
    }
    OUTPUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Exported generated data to {OUTPUT_PATH}")
    print(f"Products: {len(data['products'])}")
    print(f"Users: {len(data['users'])}")


if __name__ == "__main__":
    main()
