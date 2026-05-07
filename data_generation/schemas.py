from __future__ import annotations

from pydantic import BaseModel, Field


class SeedProduct(BaseModel):
    product_id: str
    title: str
    category: str
    price: float
    description: str
    tag: list[str] = Field(default_factory=list)
    hot_score: float = 0.0
    stock: int = 0


class SeedBehavior(BaseModel):
    product_id: str
    behavior_type: str
    weight: float = 1.0


class SeedUser(BaseModel):
    user_id: str
    segments: list[str] = Field(default_factory=list)
    behaviors: list[SeedBehavior] = Field(default_factory=list)
