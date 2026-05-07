from __future__ import annotations

import json
import math
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import get_settings

from .schemas import SeedBehavior, SeedProduct, SeedUser


PRODUCT_SYSTEM_PROMPT = """你是电商测试数据生成器。你只输出JSON数组，不要输出解释、Markdown或代码块。

每个商品必须包含这些字段:
product_id: 字符串，格式 P001、P002
title: 中文商品标题
category: 中文类目
price: 数字
description: 中文商品描述，适合做语义召回
tag: 字符串数组
hot_score: 0到100的数字
stock: 非负整数

多样性硬性要求:
1. 不要生成重复或高度相似的商品标题。
2. 同一类目下要覆盖不同子品类、品牌风格、规格、价格带和使用场景。
3. 食品类不要只生成同一种水果或同一种零食；需要覆盖水果、坚果、饼干、饮品、乳制品、即食食品、生鲜、冲调、代餐等。
4. 数码类要覆盖耳机、手机、平板、电脑、键鼠、充电器、移动电源、显示器、智能穿戴等。
5. 户外类要覆盖鞋服、背包、帐篷、登山杖、照明、户外电源、防晒、防水装备等。
6. 每个 title 必须包含能区分商品的品牌/系列/规格/场景词，避免只有类目名不同。
7. description 和 tag 必须与 title 对应，不要套用同一段促销话术。
"""

USER_SYSTEM_PROMPT = """你是电商用户测试数据生成器。你只输出JSON数组，不要输出解释、Markdown或代码块。

每个用户必须包含这些字段:
user_id: 字符串，格式 U001、U002，第一位用户必须是 web_user
segments: 字符串数组，例如 active、commuter、outdoor、price_sensitive、high_value
behaviors: 数组，每个元素包含 product_id、behavior_type、weight

behavior_type 只能从 view、click、cart、purchase、favorite 中选择。
product_id 必须来自用户给你的商品ID列表。
weight 必须是正数，view约1.0，click约1.5，favorite约2.0，cart约2.5，purchase约4.0。
"""


class LLMDataGenerator:
    """Generates seed products and users with the configured data generation LLM."""

    def __init__(self):
        self.settings = get_settings()
        self.llm = ChatOpenAI(
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            model=self.settings.data_generation_model or self.settings.llm_model,
            temperature=0.8,
            max_tokens=self.settings.data_generation_max_tokens,
        )

    async def generate(self) -> tuple[list[SeedProduct], list[SeedUser]]:
        products = await self.generate_products(
            count=self.settings.data_generation_product_count,
            categories=self._categories(),
        )
        users = await self.generate_users(
            products=products,
            count=self.settings.data_generation_user_count,
            behaviors_per_user=self.settings.data_generation_behaviors_per_user,
        )
        return products, users

    async def generate_products(
        self,
        count: int,
        categories: list[str],
    ) -> list[SeedProduct]:
        products: list[SeedProduct] = []
        seen = set()
        batch_size = max(1, self.settings.data_generation_batch_size)
        batch_count = math.ceil(count / batch_size)
        max_batches = batch_count + 5

        for batch_index in range(max_batches):
            if len(products) >= count:
                break
            current_count = min(batch_size, count - len(products))
            start_index = len(products) + 1
            existing_titles = [product.title for product in products[-80:]]
            prompt = f"""请生成 {current_count} 个电商商品测试数据。

类目范围: {", ".join(categories)}

已经生成过的商品标题，新的商品不能与它们重复或高度相似:
{json.dumps(existing_titles, ensure_ascii=False)}

要求:
1. 商品覆盖不同价格带和不同类目。
2. description 要包含用途、场景、人群、关键卖点。
3. tag 需要适合搜索和推荐召回。
4. 不要使用真实库存承诺语气，只生成测试数据。
5. product_id 从 P{start_index:03d} 开始连续递增。
6. 本批次内部 title 也不能重复，不能只改变重量、数量、包装就当作新商品。
7. 如果生成食品生鲜，请分散到不同品类，避免连续生成车厘子、草莓、坚果中的同一种商品。
8. hot_score、price、stock 要有差异，不要所有商品数值接近。
"""
            response = await self.llm.ainvoke(
                [
                    SystemMessage(content=PRODUCT_SYSTEM_PROMPT),
                    HumanMessage(content=prompt),
                ]
            )
            raw_items = self._parse_json_array(response.content)
            for offset, item in enumerate(raw_items, start=0):
                normalized = self._normalize_product(item, start_index + offset)
                title_key = self._title_key(normalized.title)
                if normalized.product_id in seen or title_key in seen:
                    continue
                if self._is_too_similar_to_existing(normalized.title, products):
                    continue
                seen.add(normalized.product_id)
                seen.add(title_key)
                products.append(normalized)
                if len(products) >= count:
                    break

        return products[:count]

    async def generate_users(
        self,
        products: list[SeedProduct],
        count: int,
        behaviors_per_user: int,
    ) -> list[SeedUser]:
        product_brief = [
            {
                "product_id": p.product_id,
                "title": p.title,
                "category": p.category,
                "tag": p.tag,
            }
            for p in products
        ]
        valid_ids = {product.product_id for product in products}
        users: list[SeedUser] = []
        seen = set()
        batch_size = max(1, self.settings.data_generation_batch_size)
        batch_count = math.ceil(count / batch_size)

        for batch_index in range(batch_count):
            current_count = min(batch_size, count - len(users))
            start_index = len(users) + 1
            first_user_rule = "第一位用户必须是 web_user。" if start_index == 1 else ""
            prompt = f"""请基于以下商品生成 {current_count} 个用户测试数据。

每个用户生成约 {behaviors_per_user} 条行为。
{first_user_rule}
非第一位用户 user_id 从 U{start_index:03d} 开始连续递增。

商品列表:
{json.dumps(product_brief, ensure_ascii=False)}
"""
            response = await self.llm.ainvoke(
                [
                    SystemMessage(content=USER_SYSTEM_PROMPT),
                    HumanMessage(content=prompt),
                ]
            )
            raw_items = self._parse_json_array(response.content)
            for offset, item in enumerate(raw_items, start=0):
                normalized = self._normalize_user(
                    item=item,
                    index=start_index + offset,
                    valid_product_ids=valid_ids,
                    behaviors_per_user=behaviors_per_user,
                )
                if start_index == 1 and offset == 0:
                    normalized.user_id = "web_user"
                if normalized.user_id in seen:
                    continue
                seen.add(normalized.user_id)
                users.append(normalized)
                if len(users) >= count:
                    break

        if users and users[0].user_id != "web_user":
            users[0].user_id = "web_user"
        return users[:count]

    def _normalize_product(self, item: dict[str, Any], index: int) -> SeedProduct:
        product_id = str(item.get("product_id") or f"P{index:03d}")
        title = str(item.get("title") or item.get("name") or f"测试商品{index}")
        category = str(item.get("category") or "其他")
        tag = item.get("tag") or item.get("tags") or []
        if isinstance(tag, str):
            tag = [tag]
        if not isinstance(tag, list):
            tag = []
        return SeedProduct(
            product_id=product_id,
            title=title,
            category=category,
            price=float(item.get("price") or 0),
            description=str(item.get("description") or title),
            tag=[str(value) for value in tag],
            hot_score=float(item.get("hot_score") or 0),
            stock=int(item.get("stock") or 0),
        )

    def _normalize_user(
        self,
        item: dict[str, Any],
        index: int,
        valid_product_ids: set[str],
        behaviors_per_user: int,
    ) -> SeedUser:
        user_id = str(item.get("user_id") or f"U{index:03d}")
        segments = item.get("segments") or []
        if isinstance(segments, str):
            segments = [segments]
        if not isinstance(segments, list):
            segments = []

        behaviors = []
        raw_behaviors = item.get("behaviors") or []
        if isinstance(raw_behaviors, list):
            for raw in raw_behaviors:
                if not isinstance(raw, dict):
                    continue
                product_id = str(raw.get("product_id") or "")
                if product_id not in valid_product_ids:
                    continue
                behaviors.append(
                    SeedBehavior(
                        product_id=product_id,
                        behavior_type=str(raw.get("behavior_type") or "view"),
                        weight=float(raw.get("weight") or 1.0),
                    )
                )

        return SeedUser(
            user_id=user_id,
            segments=[str(value) for value in segments],
            behaviors=behaviors[:behaviors_per_user],
        )

    def _parse_json_array(self, raw: str) -> list[dict[str, Any]]:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
        data = json.loads(cleaned)
        if not isinstance(data, list):
            raise ValueError("LLM data generation response must be a JSON array")
        return [item for item in data if isinstance(item, dict)]

    def _categories(self) -> list[str]:
        return [
            category.strip()
            for category in self.settings.data_generation_categories.split(",")
            if category.strip()
        ]

    def _title_key(self, title: str) -> str:
        return re.sub(r"[\W_]+", "", title.lower())

    def _is_too_similar_to_existing(
        self,
        title: str,
        products: list[SeedProduct],
    ) -> bool:
        tokens = self._title_tokens(title)
        if not tokens:
            return False
        for product in products:
            other_tokens = self._title_tokens(product.title)
            if not other_tokens:
                continue
            overlap = len(tokens & other_tokens) / max(len(tokens | other_tokens), 1)
            if overlap >= 0.72:
                return True
        return False

    def _title_tokens(self, title: str) -> set[str]:
        normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", title.lower())
        parts = {part for part in normalized.split() if len(part) >= 2}
        cjk = re.findall(r"[\u4e00-\u9fff]{2,}", title)
        for text in cjk:
            parts.update(text[index : index + 2] for index in range(len(text) - 1))
        return parts
