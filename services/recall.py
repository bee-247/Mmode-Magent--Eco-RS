from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import get_settings
from models.schemas import UserProfile
from repositories import ProductRepository
from services.embedding import EmbeddingService
from services.vector_store import MilvusVectorStore


RecallMode = Literal["user_embedding", "query_embedding"]


@dataclass
class RecallDecision:
    mode: RecallMode
    query: str = ""
    categories: list[str] = field(default_factory=list)
    reason: str = ""


class RecallDecisionAgent:
    """Uses an intent agent to choose coarse recall mode."""

    SYSTEM_PROMPT = """你是电商推荐召回意图判断Agent。你只输出JSON，不要解释。

你需要判断用户当前意图:
1. history_preference: 用户明确想根据自己看过、浏览过、买过、喜欢过、历史记录、猜你喜欢、继续推荐类似历史兴趣的商品进行推荐。
2. new_need: 用户提出了新的明确购物需求、商品、场景、关键词或图片理解结果，需要按新需求召回。

非常重要:
- 不要因为用户说了“最近”就判断为 history_preference。
- “最近想买/最近想吃/最近想找/最近需要/最近打算买”都是 new_need。
- 只有“最近看过/最近浏览过/我之前看过/根据我的历史/我喜欢过/猜你喜欢/继续推荐类似我喜欢的”才是 history_preference。
- 用户说“手机、耳机、数码设备、食品、生鲜、运动装备”等商品词、子品类或大类时，仍然判断为 new_need，用 query embedding 召回。
- 不要输出 category_rule。

例子:
- “给我推荐几个我最近看的商品” => history_preference
- “根据我的浏览历史推荐” => history_preference
- “我最近想吃点零食，有什么推荐吗” => new_need，query应包含“零食”
- “我最近想买降噪耳机” => new_need，query应包含“降噪耳机”
- “我想进行户外运动，请给我推荐装备” => new_need，query应包含“户外运动装备”
- “推荐食品生鲜类商品” => new_need，query应包含“食品生鲜”
- “推荐一些手机” => new_need，query应包含“手机”
- “推荐一些数码设备” => new_need，query应包含“数码设备”

输出格式:
{
  "intent": "history_preference" | "new_need",
  "query": "用于新需求召回的查询文本",
  "categories": ["类目1"],
  "reason": "简短原因"
}
"""

    HISTORY_KEYWORDS = [
        "最近看过",
        "最近浏览过",
        "浏览过",
        "看过的",
        "我的历史",
        "历史记录",
        "之前看过",
        "之前浏览",
        "喜欢过",
        "猜你喜欢",
        "继续推荐",
        "类似我",
    ]

    def __init__(self):
        settings = get_settings()
        self.llm = ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=0.0,
            max_tokens=512,
        )

    async def decide(
        self,
        user_id: str,
        profile: UserProfile | None,
        context: dict[str, Any],
        has_user_embedding: bool,
    ) -> RecallDecision:
        forced = context.get("recall_mode")
        query = str(context.get("query") or context.get("keyword") or "").strip()
        categories = self._extract_categories(context, profile)
        if forced in {"user_embedding", "query_embedding"}:
            return RecallDecision(
                mode=forced,
                query=query,
                categories=categories,
                reason="forced_by_context",
            )

        if query:
            llm_decision = await self._decide_with_llm(
                query=query,
                categories=categories,
                context=context,
                has_user_embedding=has_user_embedding,
            )
            if llm_decision:
                return llm_decision

            if self._looks_like_history_intent(query):
                return self._history_decision(
                    has_user_embedding=has_user_embedding,
                    categories=categories,
                    reason="history_intent_keyword_fallback",
                )

            return RecallDecision(
                mode="query_embedding",
                query=query,
                categories=categories,
                reason="new_query_fallback_to_query_embedding",
            )
        if has_user_embedding:
            return RecallDecision(
                mode="user_embedding",
                categories=categories,
                reason="user_embedding_available",
            )
        return RecallDecision(
            mode="query_embedding",
            query=query,
            categories=categories,
            reason="fallback_to_query_embedding",
        )

    async def _decide_with_llm(
        self,
        query: str,
        categories: list[str],
        context: dict[str, Any],
        has_user_embedding: bool,
    ) -> RecallDecision | None:
        payload = {
            "user_query": query,
            "known_categories": categories,
            "has_user_embedding": has_user_embedding,
            "source": context.get("source", ""),
            "image_summary": context.get("image_summary", ""),
            "image_attributes": context.get("image_attributes", []),
        }
        try:
            response = await self.llm.ainvoke(
                [
                    SystemMessage(content=self.SYSTEM_PROMPT),
                    HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
                ]
            )
            data = self._parse_json_object(response.content)
        except Exception:
            return None

        intent = str(data.get("intent") or "")
        decided_categories = data.get("categories") or categories
        if isinstance(decided_categories, str):
            decided_categories = [decided_categories]
        if not isinstance(decided_categories, list):
            decided_categories = categories
        decided_categories = [str(item) for item in decided_categories if item]
        reason = str(data.get("reason") or f"llm_intent_{intent}")

        if intent == "history_preference":
            return self._history_decision(
                has_user_embedding=has_user_embedding,
                categories=decided_categories,
                reason=reason,
            )
        if intent == "new_need":
            return RecallDecision(
                mode="query_embedding",
                query=str(data.get("query") or query),
                categories=decided_categories,
                reason=reason,
            )
        return None

    def _history_decision(
        self,
        has_user_embedding: bool,
        categories: list[str],
        reason: str,
    ) -> RecallDecision:
        if has_user_embedding:
            return RecallDecision(
                mode="user_embedding",
                categories=categories,
                reason=reason,
            )
        return RecallDecision(
            mode="query_embedding",
            query="",
            categories=categories,
            reason=f"{reason}_but_no_user_embedding",
        )

    def _looks_like_history_intent(self, query: str) -> bool:
        return any(keyword in query for keyword in self.HISTORY_KEYWORDS)

    def _parse_json_object(self, raw: str) -> dict[str, Any]:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else {}

    def _extract_categories(
        self, context: dict[str, Any], profile: UserProfile | None
    ) -> list[str]:
        raw = context.get("categories") or context.get("category") or []
        if isinstance(raw, str):
            categories = [raw]
        elif isinstance(raw, list):
            categories = [str(item) for item in raw]
        else:
            categories = []
        return [category for category in categories if category]


class VectorRecallService:
    """Runs vector coarse recall, then hydrates product details from product DB."""

    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.vector_store = MilvusVectorStore()
        self.product_repository = ProductRepository()

    async def recall_by_user_embedding(
        self,
        user_id: str,
        profile: UserProfile | None,
        limit: int,
    ):
        user_embedding = await self.vector_store.get_user_embedding(user_id)
        if not user_embedding:
            return []
        product_ids = await self.vector_store.search_products(user_embedding, limit)
        return await self.product_repository.get_products_by_ids(
            product_ids=product_ids,
            profile=profile,
        )

    async def recall_by_query(
        self,
        query: str,
        profile: UserProfile | None,
        categories: list[str],
        limit: int,
    ):
        query_vector = await self.embedding_service.embed_text(query)
        if not query_vector:
            return []
        product_ids = await self.vector_store.search_products(query_vector, limit)
        return await self.product_repository.get_products_by_ids(
            product_ids=product_ids,
            profile=profile,
            categories=categories or None,
        )
