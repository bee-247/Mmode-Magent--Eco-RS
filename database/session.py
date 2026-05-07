from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import get_settings

from .models import ProductBase, UserBase


settings = get_settings()
product_database_url = settings.product_database_url or settings.database_url
user_database_url = settings.user_database_url or settings.database_url

product_engine = create_engine(
    product_database_url,
    connect_args={"check_same_thread": False}
    if product_database_url.startswith("sqlite")
    else {},
    future=True,
)
user_engine = create_engine(
    user_database_url,
    connect_args={"check_same_thread": False}
    if user_database_url.startswith("sqlite")
    else {},
    future=True,
)

ProductSessionLocal = sessionmaker(
    bind=product_engine, autoflush=False, autocommit=False, future=True
)
UserSessionLocal = sessionmaker(
    bind=user_engine, autoflush=False, autocommit=False, future=True
)

SessionLocal = ProductSessionLocal


def init_db() -> None:
    """Create database tables only; this intentionally does not seed products."""
    ProductBase.metadata.create_all(bind=product_engine)
    UserBase.metadata.create_all(bind=user_engine)
