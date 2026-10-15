# FIA Architecture

## Goal
Independent India-first fashion product research assistant. Research autonomy only: no store accounts, carts, checkout or payments.

## Components
- FastAPI handles validation and reads.
- Research coordinator calls a provider, optionally fetches a limited set of pages, normalizes and scores results, then persists products and price observations.
- Search provider interface separates vendors; demo fixtures support offline development and Brave is optional.
- Page fetcher validates HTTP(S), rejects non-global resolved addresses, consults robots.txt, fails closed on unavailable/denied policy, refuses redirects, enforces timeout, content type and byte limits.
- Extractor parses JSON-LD Product/Offer and conservative metadata fallbacks.
- Trust layer exposes domain-match and HTTPS evidence with explicit reasons. A known retailer domain does not verify a third-party marketplace seller.
- SQLAlchemy persists research jobs, products, price observations, retailer evidence and preferences.
- React dashboard consumes the versioned API.

## Lifecycle
queued -> running -> completed | failed. The initial worker is an in-process asyncio task; this is for local/single-process use, not durable multi-worker production. A future release should use a persistent task queue with retries and lease management.

## Scoring
Initial relevance uses lexical overlap and budget fit. It is not marketed as an AI style score. Visual embeddings, fashion attributes, multilingual query expansion and feedback-driven ranking require evaluation data before activation.

## Provenance
Product records retain canonical URL, source, retailer domain and last-seen timestamps. External page data is untrusted; parse it as data, never execute scripts or obey page-embedded instructions.

## Extensions
Implement the SearchProvider contract for more search vendors or retailer feeds. Retailer-specific connectors must document permission and terms, isolate parsing, and include contract tests.
