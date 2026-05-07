"""
Multi-Agent E-Commerce Recommendation System — FastAPI Entry Point

Endpoints:
  POST /api/v1/recommend          - 获取个性化推荐
  POST /api/v1/recommend/graph    - 通过LangGraph pipeline推荐
  GET  /api/v1/experiments        - 查看A/B实验状态
  GET  /api/v1/metrics            - 查看系统监控指标
  GET  /health                    - 健康检查
"""

from __future__ import annotations

import sys
import os
import base64

sys.path.insert(0, os.path.dirname(__file__))

from contextlib import asynccontextmanager
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import get_settings
from database import init_db
from agents import ImageUnderstandingAgent
from models.schemas import ChatRequest, ChatResponse, RecommendationRequest, RecommendationResponse
from orchestrator.supervisor import SupervisorOrchestrator
from orchestrator.graph import build_recommendation_graph
from services.ab_test import ABTestEngine
from services.metrics import MetricsCollector
from services.vector_indexing import VectorIndexingService
from repositories import ProductRepository

logger = structlog.get_logger()
settings = get_settings()


ab_engine = ABTestEngine()
metrics_collector = MetricsCollector()
supervisor = SupervisorOrchestrator(ab_engine=ab_engine)
vector_indexing_service = VectorIndexingService()
image_understanding_agent = ImageUnderstandingAgent()
product_repository = ProductRepository()
rec_graph = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global rec_graph
    init_db()
    rec_graph = build_recommendation_graph()
    logger.info("app.startup", model=settings.llm_model)
    yield
    logger.info("app.shutdown")


app = FastAPI(
    title="Multi-Agent E-Commerce Recommendation System",
    description="用户画像Agent + 商品推荐Agent + 营销文案Agent + 库存决策Agent，并行+聚合模式",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def chat_page():
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/health")
async def health():
    return {"status": "healthy", "model": settings.llm_model}


@app.post("/api/v1/recommend", response_model=RecommendationResponse)
async def recommend(request: RecommendationRequest):
    """使用Supervisor编排器进行推荐 (生产推荐用法)"""
    response = await supervisor.recommend(request)
    _collect_metrics(response)
    return response


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Web chat entry: turn a user message into an agent recommendation request."""
    context: dict[str, Any] = {
        "query": request.message,
        "source": "web_chat",
    }
    if request.category:
        context["category"] = request.category
    if request.recall_mode and request.recall_mode != "auto":
        context["recall_mode"] = request.recall_mode

    rec_request = RecommendationRequest(
        user_id=request.user_id,
        scene="chat",
        num_items=request.num_items,
        context=context,
    )
    response = await supervisor.recommend(rec_request)
    _collect_metrics(response)
    product_result = response.agent_results.get("product_rec")
    return ChatResponse(
        answer=_build_chat_answer(request.message, response),
        recall_strategy=getattr(product_result, "recall_strategy", "")
        if product_result
        else "",
        recall_reason=product_result.data.get("recall_reason", "")
        if product_result
        else "",
        recommendation=response,
    )


@app.post("/api/v1/chat/image", response_model=ChatResponse)
async def chat_with_image(
    message: str = Form(""),
    image: UploadFile = File(...),
):
    """Multimodal chat entry: understand an uploaded image before recommendation."""
    image_bytes = await image.read()
    content_type = image.content_type or "image/jpeg"
    image_data_url = (
        f"data:{content_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    )

    available_categories = await product_repository.list_active_categories()
    image_result = await image_understanding_agent.run(
        image_data_url=image_data_url,
        message=message,
        available_categories=available_categories,
    )
    query = image_result.data.get("query") or message or "根据图片推荐相似商品"
    category = image_result.data.get("category") or None

    context: dict[str, Any] = {
        "query": query,
        "source": "web_image_chat",
        "recall_mode": "query_embedding",
        "skip_category_filter": True,
        "image_summary": image_result.data.get("summary", ""),
        "image_attributes": image_result.data.get("attributes", []),
        "image_category": category or "",
    }

    rec_request = RecommendationRequest(
        user_id="web_user",
        scene="image_chat",
        num_items=6,
        context=context,
    )
    response = await supervisor.recommend(rec_request)
    response.agent_results["image_understanding"] = image_result
    _collect_metrics(response)

    product_result = response.agent_results.get("product_rec")
    return ChatResponse(
        answer=_build_image_chat_answer(message, image_result.data, response),
        recall_strategy=getattr(product_result, "recall_strategy", "")
        if product_result
        else "",
        recall_reason=product_result.data.get("recall_reason", "")
        if product_result
        else "",
        recommendation=response,
    )


@app.post("/api/v1/recommend/graph")
async def recommend_via_graph(request: RecommendationRequest):
    """使用LangGraph状态图进行推荐 (展示LangGraph能力)"""
    if not rec_graph:
        return {"error": "Graph not initialized"}
    state = {
        "user_id": request.user_id,
        "scene": request.scene,
        "num_items": request.num_items,
        "context": request.context,
    }
    result = await rec_graph.ainvoke(state)
    return {
        "request_id": result.get("request_id"),
        "user_id": result.get("user_id"),
        "products": [p.model_dump() for p in result.get("final_products", [])],
        "marketing_copies": result.get("marketing_copies", []),
        "experiment_group": result.get("experiment_group", "control"),
        "total_latency_ms": round(result.get("total_latency_ms", 0), 1),
    }


@app.get("/api/v1/experiments")
async def get_experiments():
    """查看所有A/B实验状态"""
    experiments = {}
    for exp_id, exp in ab_engine.experiments.items():
        experiments[exp_id] = {
            "name": exp.name,
            "enabled": exp.enabled,
            "groups": [
                {
                    "name": g.name,
                    "weight": g.weight,
                    "config": g.config,
                    "successes": g.successes,
                    "failures": g.failures,
                }
                for g in exp.groups
            ],
            "stats": ab_engine.get_stats(exp_id),
        }
    return experiments


@app.get("/api/v1/metrics")
async def get_metrics():
    """查看系统监控指标"""
    return {
        "agents": metrics_collector.get_agent_stats(),
        "business": metrics_collector.get_business_stats(),
    }


@app.post("/api/v1/vector-index/products")
async def index_products(limit: int = 1000):
    """Encode product title/name + description into the product vector collection."""
    return await vector_indexing_service.index_products(limit=limit)


@app.post("/api/v1/vector-index/users/{user_id}")
async def index_user(user_id: str, history_limit: int = 50):
    """Encode a user's product interaction history into the user vector collection."""
    success = await vector_indexing_service.index_user(
        user_id=user_id,
        history_limit=history_limit,
    )
    return {"user_id": user_id, "indexed": success}


@app.post("/api/v1/experiments/{experiment_id}/outcome")
async def record_outcome(experiment_id: str, group: str, success: bool):
    """记录A/B测试结果,更新Thompson Sampling"""
    ab_engine.record_outcome(experiment_id, group, success)
    return {"status": "recorded"}


def _collect_metrics(response: RecommendationResponse):
    for name, result in response.agent_results.items():
        metrics_collector.record_agent_call(
            agent_name=name,
            success=result.success,
            latency_ms=result.latency_ms,
        )


def _build_chat_answer(message: str, response: RecommendationResponse) -> str:
    count = len(response.products)
    strategy = ""
    product_result = response.agent_results.get("product_rec")
    if product_result:
        strategy = product_result.data.get("recall_reason", "")

    if count == 0:
        return (
            "我已经理解你的需求，但当前商品库或库存里没有可推荐的商品。"
            "可以先导入商品、库存并建立向量索引后再试。"
        )

    lines = [f"我根据你的需求「{message}」找到了这些推荐："]
    lines.extend(_format_product_lines(response))
    return "\n".join(lines)


def _build_image_chat_answer(
    message: str,
    image_data: dict[str, Any],
    response: RecommendationResponse,
) -> str:
    count = len(response.products)
    summary = image_data.get("summary") or "图片内容"
    category = image_data.get("category") or "相关类目"
    if count == 0:
        return (
            f"我看到了{summary}，并尝试根据图片特征进行向量召回，"
            "但当前商品库、库存或向量索引里没有匹配结果。"
        )

    user_text = f"结合你的补充「{message}」，" if message else ""
    lines = [
        f"我看到了{summary}，{user_text}根据图片特征找到了这些推荐："
    ]
    lines.extend(_format_product_lines(response))
    return "\n".join(lines)


def _format_product_lines(response: RecommendationResponse) -> list[str]:
    copy_by_product = {
        item.get("product_id"): item.get("copy", "")
        for item in response.marketing_copies
        if item.get("product_id")
    }
    lines = []
    for index, product in enumerate(response.products, start=1):
        line = f"{index}. {product.name}，¥{product.price:.2f}"
        if product.category:
            line += f"，{product.category}"
        copy = copy_by_product.get(product.product_id)
        if copy:
            line += f"\n   {copy}"
        lines.append(line)
    return lines


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
