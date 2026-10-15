import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, func, select

from fia.config import get_settings
from fia.db import Base, SessionLocal, engine
from fia.models import Product, ResearchJob, RetailerEvidence, UserPreference
from fia.research import create_job, schedule_research
from fia.schemas import PreferenceUpdate, ResearchRequest

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list,
                   allow_credentials=False, allow_methods=["GET", "POST", "PUT"],
                   allow_headers=["Content-Type"])


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "environment": settings.app_env,
            "provider": settings.search_provider, "mode": "research_only", "version": app.version}


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
        # Return products associated with this query's timestamp window, not arbitrary latest catalogue rows.
        rows = db.scalars(select(Product).where(Product.last_seen >= job.created_at)
                          .order_by(desc(Product.last_seen)).limit(max(job.result_count, 50))).all()
        output = []
        for row in rows:
            try:
                evidence = json.loads(row.evidence_json or "{}")
            except json.JSONDecodeError:
                evidence = {}
            output.append({"id": row.id, "title": row.title, "canonical_url": row.canonical_url,
                           "description": row.description, "brand": row.brand, "category": row.category,
                           "image_url": row.image_url, "price": row.price, "currency": row.currency,
                           "retailer_domain": row.retailer_domain, "retailer_name": row.retailer_name,
                           "source": row.source, "availability": row.availability,
                           "trust_score": evidence.get("trust_score", 0),
                           "trust_label": evidence.get("trust_label", "Unverified"),
                           "reasons": evidence.get("reasons", [])})
        return {"job_id": job.id, "status": job.status, "query": job.query,
                "result_count": job.result_count, "error": job.error, "products": output[:job.result_count]}


@app.get("/api/v1/products")
def list_products(limit: int = Query(50, ge=1, le=200), q: str | None = None):
    with SessionLocal() as db:
        statement = select(Product).order_by(desc(Product.last_seen)).limit(limit)
        if q:
            statement = (select(Product).where(Product.title.ilike(f"%{q[:100]}%"))
                         .order_by(desc(Product.last_seen)).limit(limit))
        return [{"id": item.id, "title": item.title, "url": item.canonical_url,
                 "price": item.price, "currency": item.currency, "domain": item.retailer_domain,
                 "retailer": item.retailer_name, "image_url": item.image_url, "source": item.source}
                for item in db.scalars(statement).all()]


@app.get("/api/v1/retailers")
def list_retailers():
    with SessionLocal() as db:
        rows = db.scalars(select(RetailerEvidence).order_by(desc(RetailerEvidence.updated_at))).all()
        return [{"domain": row.domain, "name": row.retailer_name, "https": row.https,
                 "confidence": row.confidence, "notes": row.evidence_notes} for row in rows]


@app.get("/api/v1/preferences")
def get_preferences():
    with SessionLocal() as db:
        row = db.get(UserPreference, 1)
        if row is None:
            return {"preferred_categories": [], "preferred_brands": [], "preferred_colours": [],
                    "sizes": {}, "style_notes": "", "budget_default": None}
        return {"preferred_categories": json.loads(row.preferred_categories),
                "preferred_brands": json.loads(row.preferred_brands),
                "preferred_colours": json.loads(row.preferred_colours),
                "sizes": json.loads(row.sizes), "style_notes": row.style_notes,
                "budget_default": row.budget_default}


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
        row.updated_at = datetime.now(UTC)
        db.add(row)
        db.commit()
    return {"status": "saved"}


@app.get("/api/v1/stats")
def stats():
    with SessionLocal() as db:
        return {"products": db.scalar(select(func.count(Product.id))) or 0,
                "research_jobs": db.scalar(select(func.count(ResearchJob.id))) or 0,
                "completed_jobs": db.scalar(select(func.count(ResearchJob.id)).where(
                    ResearchJob.status == "completed")) or 0}
