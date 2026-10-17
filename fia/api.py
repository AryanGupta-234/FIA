import asyncio
import json
import os
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, func, or_, select

from fia.automation import auto_refresh_loop
from fia.config import get_settings
from fia.db import SessionLocal, init_db
from fia.models import (
    PriceAlert,
    PriceObservation,
    Product,
    ResearchJob,
    ResearchResult,
    RetailerEvidence,
    SavedProduct,
    SavedSearch,
    UserPreference,
)
from fia.research import create_job, schedule_research
from fia.schemas import PreferenceUpdate, ResearchRequest, SavedSearchCreate, SavedSearchUpdate
from fia.services.freshness import price_freshness
from prixon.api import agent_loop
from prixon.api import router as prixon_router
from prixon.config import PrixonSettings

settings = get_settings()


def _iso_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _product_payload(
    product: Product,
    result: ResearchResult | None = None,
    is_saved: bool = False,
):
    try:
        evidence = json.loads(product.evidence_json or "{}")
    except json.JSONDecodeError:
        evidence = {}
    try:
        reasons = json.loads(result.reasons_json) if result else evidence.get("reasons", [])
    except json.JSONDecodeError:
        reasons = evidence.get("reasons", [])
    return {
        "id": product.id,
        "title": product.title,
        "canonical_url": product.canonical_url,
        "description": product.description,
        "brand": product.brand,
        "category": product.category,
        "product_type": product.product_type,
        "colour": product.colour,
        "material": product.material,
        "fit": product.fit,
        "size_label": product.size_label,
        "gender": product.gender,
        "sku": product.sku,
        "gtin": product.gtin,
        "image_url": product.image_url,
        "image_source": product.image_source,
        "price": product.price,
        "original_price": product.original_price,
        "discount_percent": product.discount_percent,
        "currency": product.currency,
        "availability": product.availability,
        "seller_name": product.seller_name,
        "offer_label": product.offer_label,
        "offer_valid_until": product.offer_valid_until,
        "retailer_domain": product.retailer_domain,
        "retailer_name": product.retailer_name,
        "source": product.source,
        "last_seen": _iso_timestamp(product.last_seen),
        "price_checked_at": _iso_timestamp(product.price_checked_at),
        "price_freshness": price_freshness(
            product.price_checked_at, settings.price_stale_after_hours
        )["status"],
        "price_age_hours": price_freshness(
            product.price_checked_at, settings.price_stale_after_hours
        )["age_hours"],
        "relevance_score": result.relevance_score if result else 0,
        "trust_score": result.trust_score if result else evidence.get("trust_score", 0),
        "trust_label": evidence.get("trust_label", "Unverified"),
        "reasons": reasons,
        "is_saved": is_saved,
    }


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    scheduler = asyncio.create_task(auto_refresh_loop())
    prixon_settings = PrixonSettings()
    if os.name == "nt" and prixon_settings.agent_autostart:
        await agent_loop.start()
    try:
        yield
    finally:
        if agent_loop.running:
            await agent_loop.stop("api_shutdown")
        scheduler.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler


app = FastAPI(title=settings.app_name, version="0.3.0", lifespan=lifespan)
app.include_router(prixon_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/api/v1/health")
def health():
    return {
        "status": "ok",
        "environment": settings.app_env,
        "provider": settings.search_provider,
        "mode": "research_only",
        "live_discovery": settings.search_provider != "demo",
        "automatic_offer_refresh": (
            settings.auto_refresh_enabled and settings.search_provider != "demo"
        ),
        "refresh_interval_minutes": settings.auto_refresh_interval_minutes,
        "price_stale_after_hours": settings.price_stale_after_hours,
        "price_alert_cooldown_hours": settings.price_alert_cooldown_hours,
        "default_price_alert_threshold_percent": settings.min_price_alert_drop_percent,
        "version": app.version,
    }


@app.post("/api/v1/research", status_code=202)
def start_research(payload: ResearchRequest):
    with SessionLocal() as db:
        job_id = create_job(db, payload.query, payload.budget_max, payload.category)
    schedule_research(job_id, payload.fetch_product_pages, payload.limit)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/v1/research/{job_id}")
def get_research(job_id: str):
    with SessionLocal() as db:
        job = db.get(ResearchJob, job_id)
        if job is None:
            raise HTTPException(404, "Research job not found")
        rows = db.execute(
            select(ResearchResult, Product)
            .join(Product, Product.id == ResearchResult.product_id)
            .where(ResearchResult.job_id == job_id)
            .order_by(desc(ResearchResult.relevance_score), desc(ResearchResult.trust_score))
        ).all()
        products = [_product_payload(product, result) for result, product in rows]
        return {
            "job_id": job.id,
            "status": job.status,
            "query": job.query,
            "result_count": job.result_count,
            "error": job.error,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "products": products,
        }


@app.get("/api/v1/products")
def list_products(
    limit: int = Query(60, ge=1, le=200),
    q: str | None = None,
    category: str | None = None,
    budget_max: float | None = Query(None, gt=0),
):
    with SessionLocal() as db:
        statement = select(Product).order_by(desc(Product.last_seen))
        if q:
            statement = statement.where(Product.title.ilike(f"%{q[:100]}%"))
        if category and category.lower() != "any":
            statement = statement.where(Product.category.ilike(category[:80]))
        if budget_max is not None:
            statement = statement.where(Product.price.is_not(None), Product.price <= budget_max)
        rows = db.scalars(statement.limit(limit)).all()
        saved_ids = set(
            db.scalars(select(SavedProduct.product_id).where(
                SavedProduct.product_id.in_([row.id for row in rows])
            )).all()
        ) if rows else set()
        return [_product_payload(row, is_saved=row.id in saved_ids) for row in rows]


@app.get("/api/v1/products/{product_id}")
def get_product(product_id: int):
    with SessionLocal() as db:
        product = db.get(Product, product_id)
        if product is None:
            raise HTTPException(404, "Product not found")
        saved = (
            db.scalar(
                select(SavedProduct.id).where(SavedProduct.product_id == product_id)
            )
            is not None
        )
        history = db.scalars(
            select(PriceObservation).where(PriceObservation.product_id == product_id)
            .order_by(desc(PriceObservation.observed_at)).limit(30)
        ).all()
        return {
            "product": _product_payload(product, is_saved=saved),
            "price_history": [
                {
                    "price": point.price,
                    "original_price": point.original_price,
                    "discount_percent": point.discount_percent,
                    "currency": point.currency,
                    "availability": point.availability,
                    "source": point.source,
                    "observed_at": point.observed_at.isoformat(),
                }
                for point in history
            ],
        }


@app.get("/api/v1/offers")
def list_offers(
    limit: int = Query(60, ge=1, le=200),
    q: str | None = None,
    include_stale: bool = False,
):
    with SessionLocal() as db:
        statement = select(Product).where(
            Product.price.is_not(None),
            or_(
                Product.discount_percent > 0,
                Product.original_price > Product.price,
            ),
        )
        if not include_stale:
            fresh_since = datetime.now(UTC) - timedelta(hours=settings.price_stale_after_hours)
            statement = statement.where(
                Product.price_checked_at.is_not(None),
                Product.price_checked_at >= fresh_since,
            )
        if q:
            statement = statement.where(Product.title.ilike(f"%{q[:100]}%"))
        rows = db.scalars(
            statement.order_by(
                desc(Product.discount_percent), desc(Product.price_checked_at)
            ).limit(limit)
        ).all()
        return [_product_payload(row) for row in rows]


@app.get("/api/v1/products/{product_id}/matches")
def get_product_matches(product_id: int):
    """Return separate retailer listings only when they share an exact validated GTIN."""
    with SessionLocal() as db:
        product = db.get(Product, product_id)
        if product is None:
            raise HTTPException(404, "Product not found")
        if not product.gtin:
            return {"match_method": "exact_gtin", "gtin": None, "matches": []}
        matches = db.scalars(
            select(Product).where(Product.gtin == product.gtin, Product.id != product_id)
            .order_by(desc(Product.price_checked_at), desc(Product.last_seen))
            .limit(30)
        ).all()
        return {
            "match_method": "exact_gtin",
            "gtin": product.gtin,
            "matches": [_product_payload(row) for row in matches],
        }


@app.get("/api/v1/alerts")
def list_alerts(
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = False,
):
    with SessionLocal() as db:
        statement = (
            select(PriceAlert, Product)
            .join(Product, Product.id == PriceAlert.product_id)
        )
        if unread_only:
            statement = statement.where(PriceAlert.read_at.is_(None))
        rows = db.execute(
            statement.order_by(desc(PriceAlert.created_at), desc(PriceAlert.id)).limit(limit)
        ).all()
        return [
            {
                "id": alert.id,
                "product_id": product.id,
                "title": product.title,
                "image_url": product.image_url,
                "canonical_url": product.canonical_url,
                "previous_price": alert.previous_price,
                "current_price": alert.current_price,
                "currency": alert.currency,
                "drop_percent": alert.drop_percent,
                "created_at": _iso_timestamp(alert.created_at),
                "read_at": _iso_timestamp(alert.read_at),
            }
            for alert, product in rows
        ]


@app.post("/api/v1/alerts/{alert_id}/read")
def mark_alert_read(alert_id: int):
    with SessionLocal() as db:
        alert = db.get(PriceAlert, alert_id)
        if alert is None:
            raise HTTPException(404, "Price alert not found")
        if alert.read_at is None:
            alert.read_at = datetime.now(UTC)
            db.commit()
    return {"status": "read"}


@app.get("/api/v1/retailers")
def list_retailers():
    with SessionLocal() as db:
        rows = db.scalars(
            select(RetailerEvidence).order_by(desc(RetailerEvidence.updated_at))
        ).all()
        return [
            {
                "domain": row.domain,
                "name": row.retailer_name,
                "https": row.https,
                "confidence": row.confidence,
                "notes": row.evidence_notes,
            }
            for row in rows
        ]


@app.get("/api/v1/history")
def list_history(limit: int = Query(30, ge=1, le=100)):
    with SessionLocal() as db:
        rows = db.scalars(
            select(ResearchJob).order_by(desc(ResearchJob.created_at)).limit(limit)
        ).all()
        return [
            {
                "job_id": row.id,
                "query": row.query,
                "status": row.status,
                "result_count": row.result_count,
                "error": row.error,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            }
            for row in rows
        ]


@app.get("/api/v1/saved-searches")
def get_saved_searches():
    with SessionLocal() as db:
        rows = db.scalars(select(SavedSearch).order_by(desc(SavedSearch.created_at))).all()
        return [
            {
                "id": row.id,
                "query": row.query,
                "budget_max": row.budget_max,
                "category": row.category,
                "active": row.active,
                "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
                "next_refresh_at": row.next_refresh_at.isoformat() if row.next_refresh_at else None,
            }
            for row in rows
        ]


@app.post("/api/v1/saved-searches", status_code=201)
def save_search(payload: SavedSearchCreate):
    now = datetime.now(UTC)
    with SessionLocal() as db:
        row = db.scalar(
            select(SavedSearch).where(
                SavedSearch.query == payload.query,
                SavedSearch.budget_max == payload.budget_max,
                SavedSearch.category == payload.category,
            )
        )
        if row is None:
            row = SavedSearch(
                query=payload.query,
                budget_max=payload.budget_max,
                category=payload.category,
            )
            db.add(row)
        row.active = True
        row.next_refresh_at = now + timedelta(minutes=settings.auto_refresh_interval_minutes)
        db.commit()
        db.refresh(row)
        job_id = create_job(db, row.query, row.budget_max, row.category)
        row.last_run_at = now
        db.commit()
        saved_id = row.id
    schedule_research(job_id, True, 25)
    return {"id": saved_id, "job_id": job_id, "status": "watching"}


@app.put("/api/v1/saved-searches/{search_id}")
def update_saved_search(search_id: int, payload: SavedSearchUpdate):
    with SessionLocal() as db:
        row = db.get(SavedSearch, search_id)
        if row is None:
            raise HTTPException(404, "Saved search not found")
        row.active = payload.active
        db.commit()
    return {"status": "updated", "active": payload.active}


@app.delete("/api/v1/saved-searches/{search_id}")
def delete_saved_search(search_id: int):
    with SessionLocal() as db:
        row = db.get(SavedSearch, search_id)
        if row is None:
            raise HTTPException(404, "Saved search not found")
        db.delete(row)
        db.commit()
    return {"status": "deleted"}


@app.post("/api/v1/saved-searches/{search_id}/refresh", status_code=202)
def refresh_saved_search(search_id: int):
    now = datetime.now(UTC)
    with SessionLocal() as db:
        row = db.get(SavedSearch, search_id)
        if row is None:
            raise HTTPException(404, "Saved search not found")
        job_id = create_job(db, row.query, row.budget_max, row.category)
        row.last_run_at = now
        row.next_refresh_at = now + timedelta(minutes=settings.auto_refresh_interval_minutes)
        db.commit()
    schedule_research(job_id, True, 25)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/v1/saved-products")
def get_saved_products():
    with SessionLocal() as db:
        rows = db.execute(
            select(Product).join(SavedProduct, SavedProduct.product_id == Product.id)
            .order_by(desc(SavedProduct.created_at))
        ).scalars().all()
        return [_product_payload(row, is_saved=True) for row in rows]


@app.post("/api/v1/saved-products/{product_id}", status_code=201)
def save_product(product_id: int):
    with SessionLocal() as db:
        if db.get(Product, product_id) is None:
            raise HTTPException(404, "Product not found")
        row = db.scalar(select(SavedProduct).where(SavedProduct.product_id == product_id))
        if row is None:
            db.add(SavedProduct(product_id=product_id))
            db.commit()
    return {"status": "saved"}


@app.delete("/api/v1/saved-products/{product_id}")
def unsave_product(product_id: int):
    with SessionLocal() as db:
        row = db.scalar(select(SavedProduct).where(SavedProduct.product_id == product_id))
        if row is not None:
            db.delete(row)
            db.commit()
    return {"status": "removed"}


@app.get("/api/v1/preferences")
def get_preferences():
    with SessionLocal() as db:
        row = db.get(UserPreference, 1)
        if row is None:
            return {
                "preferred_categories": [],
                "preferred_brands": [],
                "preferred_colours": [],
                "sizes": {},
                "style_notes": "",
                "budget_default": None,
                "price_alert_threshold_percent": settings.min_price_alert_drop_percent,
            }
        return {
            "preferred_categories": json.loads(row.preferred_categories),
            "preferred_brands": json.loads(row.preferred_brands),
            "preferred_colours": json.loads(row.preferred_colours),
            "sizes": json.loads(row.sizes),
            "style_notes": row.style_notes,
            "budget_default": row.budget_default,
            "price_alert_threshold_percent": row.price_alert_threshold_percent,
        }


@app.put("/api/v1/preferences")
def update_preferences(payload: PreferenceUpdate):
    with SessionLocal() as db:
        row = db.get(UserPreference, 1) or UserPreference(id=1)
        row.preferred_categories = json.dumps(payload.preferred_categories)
        row.preferred_brands = json.dumps(payload.preferred_brands)
        row.preferred_colours = json.dumps(payload.preferred_colours)
        row.sizes = json.dumps(payload.sizes)
        row.style_notes = payload.style_notes
        row.budget_default = payload.budget_default
        row.price_alert_threshold_percent = payload.price_alert_threshold_percent
        row.updated_at = datetime.now(UTC)
        db.add(row)
        db.commit()
    return {"status": "saved"}


@app.get("/api/v1/stats")
def stats():
    with SessionLocal() as db:
        return {
            "products": db.scalar(select(func.count(Product.id))) or 0,
            "research_jobs": db.scalar(select(func.count(ResearchJob.id))) or 0,
            "completed_jobs": db.scalar(
                select(func.count(ResearchJob.id)).where(ResearchJob.status == "completed")
            ) or 0,
            "offers": db.scalar(
                select(func.count(Product.id)).where(
                    Product.price.is_not(None),
                    Product.price_checked_at.is_not(None),
                    Product.price_checked_at >= datetime.now(UTC) - timedelta(
                        hours=settings.price_stale_after_hours
                    ),
                    or_(Product.discount_percent > 0, Product.original_price > Product.price),
                )
            ) or 0,
            "saved_products": db.scalar(select(func.count(SavedProduct.id))) or 0,
            "saved_searches": db.scalar(select(func.count(SavedSearch.id))) or 0,
            "price_alerts_unread": db.scalar(
                select(func.count(PriceAlert.id)).where(PriceAlert.read_at.is_(None))
            ) or 0,
        }
