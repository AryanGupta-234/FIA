import asyncio
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select

from fia.config import get_settings
from fia.crawling.extractor import extract_product
from fia.crawling.fetcher import PageFetcher
from fia.db import SessionLocal
from fia.discovery.factory import get_search_provider
from fia.models import (
    PriceAlert,
    PriceObservation,
    Product,
    ResearchJob,
    ResearchResult,
    RetailerEvidence,
    SavedProduct,
)
from fia.services.normalize import canonicalize_url
from fia.services.offers import apply_price_evidence
from fia.services.ranking import rank_product
from fia.services.trust import assess_url


def create_job(db, query: str, budget_max: float | None, category: str | None) -> str:
    job_id = str(uuid.uuid4())
    db.add(
        ResearchJob(
            id=job_id,
            query=query,
            budget_max=budget_max,
            category=category,
            status="queued",
        )
    )
    db.commit()
    return job_id


def _image_match(title: str, images: list) -> str | None:
    title_terms = {part for part in title.lower().split() if len(part) > 2}
    best_url, best_score = None, 0
    for image in images:
        image_terms = {part for part in image.title.lower().split() if len(part) > 2}
        score = len(title_terms.intersection(image_terms))
        if score > best_score and image.image_url:
            best_url, best_score = image.image_url, score
    return best_url if best_score else (images[0].image_url if images else None)


async def run_research(job_id: str, fetch_pages: bool, limit: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(ResearchJob, job_id)
        if job is None:
            return
        job.status = "running"
        db.execute(delete(ResearchResult).where(ResearchResult.job_id == job_id))
        db.commit()

        settings = get_settings()
        provider = get_search_provider()
        results = await provider.search(job.query, limit)
        images = []
        if hasattr(provider, "search_images"):
            try:
                images = await provider.search_images(job.query, min(limit, 12))
            except (RuntimeError, ValueError, OSError):
                images = []

        fetcher = PageFetcher()
        products = {}
        pages = 0
        for result in results:
            try:
                canonical = canonicalize_url(result.url)
            except ValueError:
                continue
            host = canonical.split("/")[2].split(":")[0]
            item = {
                "title": result.title,
                "description": result.snippet,
                "canonical_url": canonical,
                "retailer_domain": host,
                "source": result.source or (
                    "demo" if settings.search_provider == "demo" else "brave_web"
                ),
                "currency": "INR",
                "image_url": result.image_url,
                "image_source": "search_thumbnail" if result.image_url else None,
            }
            if (
                fetch_pages
                and pages < settings.crawl_max_pages_per_job
                and settings.search_provider != "demo"
            ): 
                html, _message = await fetcher.fetch(canonical)
                pages += 1
                if html:
                    parsed = extract_product(html, canonical)
                    if parsed:
                        item.update(
                            {key: value for key, value in parsed.items() if value not in (None, "")}
                        )
                        if parsed.get("image_url"):
                            item["image_source"] = "retailer_page"
            if not item.get("image_url"):
                item["image_url"] = _image_match(item["title"], images)
                if item["image_url"]:
                    item["image_source"] = "brave_image_search"
            products[canonical] = rank_product(item, job.query, job.budget_max)

        ordered = sorted(
            products.values(),
            key=lambda item: (item["relevance_score"], item["trust_score"]),
            reverse=True,
        )
        for item in ordered:
            row = db.scalar(select(Product).where(Product.canonical_url == item["canonical_url"]))
            previous_price = row.price if row is not None else None
            previous_currency = row.currency if row is not None else "INR"
            previous_snapshot = (
                row.price,
                row.original_price,
                row.discount_percent,
                row.currency,
                row.availability,
            ) if row is not None else None
            if row is None:
                row = Product(
                    canonical_url=item["canonical_url"],
                    title=item["title"][:500],
                    retailer_domain=item["retailer_domain"],
                    source=item["source"],
                )
                db.add(row)
            row.title = item["title"][:500]
            row.description = (item.get("description") or row.description or "")[:4000]
            row.brand = item.get("brand") or row.brand
            row.category = job.category or row.category
            row.image_url = item.get("image_url") or row.image_url
            row.image_source = item.get("image_source") or row.image_source
            has_price_evidence = apply_price_evidence(row, item)
            row.seller_name = item.get("seller_name") or row.seller_name
            row.retailer_name = item.get("retailer_name") or row.retailer_name
            row.source = item["source"]
            row.evidence_json = json.dumps(
                {
                    "trust_score": item["trust_score"],
                    "trust_label": item["trust_label"],
                    "reasons": item["reasons"],
                }
            )
            row.last_seen = datetime.now(UTC)
            db.flush()

            current_snapshot = (
                row.price,
                row.original_price,
                row.discount_percent,
                row.currency,
                row.availability,
            )
            if (
                has_price_evidence
                and row.price is not None
                and current_snapshot != previous_snapshot
            ):
                db.add(
                    PriceObservation(
                        product_id=row.id,
                        price=row.price,
                        original_price=row.original_price,
                        discount_percent=row.discount_percent,
                        currency=row.currency,
                        availability=row.availability,
                        source=row.source,
                    )
                )

            if (
                previous_price is not None
                and row.price is not None
                and previous_currency == row.currency
                and previous_price - row.price > 0.01
                and db.scalar(
                    select(SavedProduct.id).where(SavedProduct.product_id == row.id)
                ) is not None
            ):
                drop_percent = round((previous_price - row.price) / previous_price * 100, 1)
                db.add(
                    PriceAlert(
                        product_id=row.id,
                        previous_price=previous_price,
                        current_price=row.price,
                        currency=row.currency,
                        drop_percent=drop_percent,
                    )
                )
            evidence = assess_url(item["canonical_url"])
            retailer = db.scalar(
                select(RetailerEvidence).where(RetailerEvidence.domain == item["retailer_domain"])
            )
            if retailer is None:
                retailer = RetailerEvidence(domain=item["retailer_domain"])
                db.add(retailer)
            retailer.retailer_name = item.get("retailer_name") or retailer.retailer_name
            retailer.official_domain_match = bool(retailer.retailer_name)
            retailer.https = evidence["https"]
            retailer.confidence = evidence["score"]
            retailer.evidence_notes = "; ".join(evidence["reasons"])
            db.add(
                ResearchResult(
                    job_id=job_id,
                    product_id=row.id,
                    relevance_score=item["relevance_score"],
                    trust_score=item["trust_score"],
                    reasons_json=json.dumps(item["reasons"]),
                )
            )

        job.status = "completed"
        job.result_count = len(ordered)
        job.completed_at = datetime.now(UTC)
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(ResearchJob, job_id)
        if job is not None:
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {str(exc)[:400]}"
            job.completed_at = datetime.now(UTC)
            db.commit()
    finally:
        db.close()


def schedule_research(job_id: str, fetch_pages: bool, limit: int) -> None:
    asyncio.create_task(run_research(job_id, fetch_pages, limit))
