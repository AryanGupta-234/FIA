import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from fia.config import get_settings
from fia.crawling.extractor import extract_product
from fia.crawling.fetcher import PageFetcher
from fia.db import SessionLocal
from fia.discovery.factory import get_search_provider
from fia.models import PriceObservation, Product, ResearchJob, RetailerEvidence
from fia.services.normalize import canonicalize_url
from fia.services.ranking import rank_product
from fia.services.trust import assess_url


def create_job(db, query: str, budget_max: float | None, category: str | None) -> str:
    job_id = str(uuid.uuid4())
    db.add(ResearchJob(id=job_id, query=query, budget_max=budget_max,
                       category=category, status="queued"))
    db.commit()
    return job_id


async def run_research(job_id: str, fetch_pages: bool, limit: int) -> None:
    db = SessionLocal()
    job = db.get(ResearchJob, job_id)
    if job is None:
        db.close()
        return
    job.status = "running"
    db.commit()
    try:
        settings = get_settings()
        results = await get_search_provider().search(job.query, limit)
        fetcher = PageFetcher()
        products = {}
        pages = 0
        for result in results:
            try:
                canonical = canonicalize_url(result.url)
            except ValueError:
                continue
            host = canonical.split("/")[2].split(":")[0]
            item = {"title": result.title, "description": result.snippet,
                    "canonical_url": canonical, "retailer_domain": host,
                    "source": "demo" if settings.search_provider == "demo" else "web_search",
                    "currency": "INR"}
            if fetch_pages and pages < settings.crawl_max_pages_per_job and settings.search_provider != "demo":
                html, _message = await fetcher.fetch(canonical)
                pages += 1
                if html:
                    parsed = extract_product(html, canonical)
                    if parsed:
                        item.update({key: value for key, value in parsed.items() if value not in (None, "")})
            item = rank_product(item, job.query, job.budget_max)
            products[canonical] = item
        ordered = sorted(products.values(),
                         key=lambda item: (item["relevance_score"], item["trust_score"]), reverse=True)
        for item in ordered:
            row = db.scalar(select(Product).where(Product.canonical_url == item["canonical_url"]))
            if row is None:
                row = Product(canonical_url=item["canonical_url"], title=item["title"][:500],
                              retailer_domain=item["retailer_domain"], source=item["source"])
                db.add(row)
            row.title = item["title"][:500]
            row.description = (item.get("description") or "")[:4000]
            row.brand = item.get("brand")
            row.category = job.category
            row.image_url = item.get("image_url")
            row.price = item.get("price")
            row.currency = item.get("currency") or "INR"
            row.availability = item.get("availability")
            row.retailer_name = item.get("retailer_name")
            row.evidence_json = __import__("json").dumps(
                {"trust_score": item["trust_score"], "trust_label": item["trust_label"],
                 "reasons": item["reasons"]})
            row.last_seen = datetime.now(UTC)
            db.flush()
            if row.price is not None and row.price > 0:
                db.add(PriceObservation(product_id=row.id, price=row.price,
                                        currency=row.currency, source=row.source))
            evidence = assess_url(item["canonical_url"])
            retailer = db.scalar(select(RetailerEvidence).where(
                RetailerEvidence.domain == item["retailer_domain"]))
            if retailer is None:
                retailer = RetailerEvidence(domain=item["retailer_domain"])
                db.add(retailer)
            retailer.retailer_name = item.get("retailer_name")
            retailer.official_domain_match = bool(item.get("retailer_name"))
            retailer.https = evidence["https"]
            retailer.confidence = evidence["score"]
            retailer.evidence_notes = "; ".join(evidence["reasons"])
        job.status = "completed"
        job.result_count = len(ordered)
        job.completed_at = datetime.now(UTC)
        db.commit()
    except (RuntimeError, ValueError, OSError) as exc:
        db.rollback()
        job = db.get(ResearchJob, job_id)
        if job:
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {str(exc)[:400]}"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


def schedule_research(job_id: str, fetch_pages: bool, limit: int) -> None:
    asyncio.create_task(run_research(job_id, fetch_pages, limit))
