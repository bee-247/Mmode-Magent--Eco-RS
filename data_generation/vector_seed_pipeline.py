from __future__ import annotations

import json
from datetime import datetime

from database import init_db
from database.models import InventoryRecord, ProductRecord, UserBehaviorRecord, UserRecord
from database.session import ProductSessionLocal, UserSessionLocal
from config import get_settings
from services.embedding import EmbeddingService
from services.vector_store import MilvusVectorStore

from .schemas import SeedProduct, SeedUser
from .vector_math import weighted_average


class VectorSeedPipeline:
    """Seeds product/user DB rows and builds product/user embeddings."""

    def __init__(self):
        self.settings = get_settings()
        self.embedding_service = EmbeddingService()
        self.vector_store = MilvusVectorStore()

    async def run(
        self,
        products: list[SeedProduct],
        users: list[SeedUser],
    ) -> dict[str, int]:
        init_db()
        if self.settings.data_generation_reset_tables:
            self.reset_tables()
        if self.settings.data_generation_reset_vectors:
            self.vector_store.reset_seed_collections()
        self.save_products(products)
        product_embeddings = await self.index_product_embeddings(products)
        self.save_users(users)
        indexed_users = await self.index_user_embeddings(users, product_embeddings)
        return {
            "products_saved": len(products),
            "product_embeddings_indexed": len(product_embeddings),
            "users_saved": len(users),
            "user_embeddings_indexed": indexed_users,
        }

    def reset_tables(self) -> None:
        with ProductSessionLocal() as session:
            session.query(InventoryRecord).delete(synchronize_session=False)
            session.query(ProductRecord).delete(synchronize_session=False)
            session.commit()

        with UserSessionLocal() as session:
            session.query(UserBehaviorRecord).delete(synchronize_session=False)
            session.query(UserRecord).delete(synchronize_session=False)
            session.commit()

    def save_products(self, products: list[SeedProduct]) -> None:
        with ProductSessionLocal() as session:
            for item in products:
                product = session.get(ProductRecord, item.product_id)
                if not product:
                    product = ProductRecord(product_id=item.product_id)
                    session.add(product)

                product.name = item.title
                product.category = item.category
                product.price = item.price
                product.description = item.description
                product.tags_json = json.dumps(item.tag, ensure_ascii=False)
                product.hot_score = item.hot_score
                product.status = "active"
                product.brand = ""
                product.seller_id = ""

                inventory = session.get(InventoryRecord, item.product_id)
                if not inventory:
                    inventory = InventoryRecord(product_id=item.product_id)
                    session.add(inventory)
                inventory.stock = item.stock
                inventory.reserved_stock = 0

            session.commit()

    async def index_product_embeddings(
        self,
        products: list[SeedProduct],
    ) -> dict[str, list[float]]:
        embeddings: dict[str, list[float]] = {}
        for product in products:
            text = self.product_embedding_text(product)
            embedding = await self.embedding_service.embed_text(text)
            if not embedding:
                continue
            embeddings[product.product_id] = embedding
            await self.vector_store.upsert_product_embedding(
                product_id=product.product_id,
                embedding=embedding,
            )
        return embeddings

    def save_users(self, users: list[SeedUser]) -> None:
        now = datetime.utcnow()
        with UserSessionLocal() as session:
            for item in users:
                user = session.get(UserRecord, item.user_id)
                if not user:
                    user = UserRecord(user_id=item.user_id)
                    session.add(user)
                user.segments_json = json.dumps(item.segments, ensure_ascii=False)
                user.preferred_categories_json = "[]"

                session.query(UserBehaviorRecord).filter(
                    UserBehaviorRecord.user_id == item.user_id,
                    UserBehaviorRecord.scene == "vector_seed",
                ).delete(synchronize_session=False)

                for behavior in item.behaviors:
                    session.add(
                        UserBehaviorRecord(
                            user_id=item.user_id,
                            product_id=behavior.product_id,
                            behavior_type=behavior.behavior_type,
                            scene="vector_seed",
                            weight=behavior.weight,
                            created_at=now,
                        )
                    )

            session.commit()

    async def index_user_embeddings(
        self,
        users: list[SeedUser],
        product_embeddings: dict[str, list[float]],
    ) -> int:
        indexed = 0
        for user in users:
            weighted_vectors = [
                (product_embeddings.get(behavior.product_id, []), behavior.weight)
                for behavior in user.behaviors
            ]
            user_embedding = weighted_average(weighted_vectors)
            if not user_embedding:
                continue
            ok = await self.vector_store.upsert_user_embedding(
                user_id=user.user_id,
                embedding=user_embedding,
            )
            if ok:
                indexed += 1
        return indexed

    def product_embedding_text(self, product: SeedProduct) -> str:
        return f"{product.title}\n{product.description}".strip()
