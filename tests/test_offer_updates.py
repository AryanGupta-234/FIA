import asyncio

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from fia.db import Base
from fia.discovery.base import SearchResult
from fia.models import PriceAlert, PriceObservation, Product, ResearchJob, SavedProduct
from fia.research import run_research


def test_research_clears_stale_discount_and_alerts_saved_product(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("fia.research.SessionLocal", factory)
    monkeypatch.setattr(
        "fia.research.get_settings",
        lambda: type(
            "Settings",
            (),
            {"search_provider": "brave", "crawl_max_pages_per_job": 8},
        )(),
    )

    class FakeProvider:
        async def search(self, query, limit=10):
            return [
                SearchResult(
                    title="Canvas low-top shoe",
                    url="https://shop.example/products/shoe",
                    source="brave_web",
                )
            ]

    class FakeFetcher:
        async def fetch(self, url):
            return "<html><title>Canvas low-top shoe</title></html>", "ok"

    monkeypatch.setattr("fia.research.get_search_provider", lambda: FakeProvider())
    monkeypatch.setattr("fia.research.PageFetcher", FakeFetcher)
    monkeypatch.setattr(
        "fia.research.extract_product",
        lambda html, url: {
            "title": "Canvas low-top shoe",
            "canonical_url": url,
            "price": 1299,
            "currency": "INR",
            "original_price": None,
            "discount_percent": None,
            "offer_label": None,
            "offer_valid_until": None,
            "availability": None,
        },
    )

    job_id = "e6a50aa1-bd61-4f5a-b50f-18a7b37a35a6"
    with factory() as db:
        db.add(ResearchJob(id=job_id, query="canvas shoe", status="queued"))
        product = Product(
            canonical_url="https://shop.example/products/shoe",
            title="Canvas low-top shoe",
            retailer_domain="shop.example",
            source="brave_web",
            price=1499,
            original_price=1999,
            discount_percent=25,
            currency="INR",
            offer_label="Old retailer promotion",
            offer_valid_until="2026-10-01",
        )
        db.add(product)
        db.flush()
        db.add(SavedProduct(product_id=product.id))
        db.commit()
        product_id = product.id

    asyncio.run(run_research(job_id, True, 5))

    with factory() as db:
        product = db.get(Product, product_id)
        job = db.get(ResearchJob, job_id)
        observations = db.scalars(
            select(PriceObservation).where(PriceObservation.product_id == product_id)
        ).all()
        alerts = db.scalars(
            select(PriceAlert).where(PriceAlert.product_id == product_id)
        ).all()
        assert job.status == "completed"
        assert product.price == 1299
        assert product.original_price is None
        assert product.discount_percent is None
        assert product.offer_label is None
        assert product.offer_valid_until is None
        assert len(observations) == 1
        assert observations[0].price == 1299
        assert len(alerts) == 1
        assert alerts[0].previous_price == 1499
        assert alerts[0].current_price == 1299
        assert alerts[0].currency == "INR"
        assert alerts[0].drop_percent == 13.3

    engine.dispose()
