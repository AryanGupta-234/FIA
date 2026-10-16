# FIA Architecture

## Product intent
FIA is a standalone, India-first fashion research workspace. It automates discovery, product-detail extraction, evidence capture, price observation and opt-in search refresh. It does not log in to stores, add cart items, check out, enter payment details or purchase.

## Runtime
- API: FastAPI, local-first, bound to 127.0.0.1 by default.
- Persistence: SQLAlchemy with SQLite default and PostgreSQL-compatible schema.
- Dashboard: React + Vite, responsive dark glass UI, first-run boot screen, discovery workspace, offer radar, saved products, search watches, history and style profile.
- Windows launcher: PowerShell opens the API and dashboard in separate terminals; optional script adds a Windows Start Menu shortcut.

## Discovery pipeline
1. A query is sent to the configured SearchProvider.
2. The Brave adapter uses India-scoped web search. A separate image search is a visual fallback when a product page does not expose an image.
3. Candidate URLs are normalized and deduplicated.
4. A small bounded number of product pages may be inspected only when robots policy permits. The fetcher accepts HTTP(S), rejects non-public DNS targets, checks robots.txt, refuses redirects, and limits time and bytes.
5. The extractor prefers JSON-LD Product/Offer and fashion attributes, then falls back to Open Graph and product price metadata.
6. The ranking layer combines lexical query match, budget fit and retailer-domain evidence with a transparent reason list.
7. Products, research-result links, fashion attributes and changed price observations are stored. Price-check timestamps drive the freshness state.

## Offer evidence
A discount is displayed only when the source provides both a current and original/reference price or an explicit structured discount. Offers older than the freshness window (72 hours by default) are excluded from the main offer feed; callers can explicitly request stale entries. FIA does not infer an offer from a promotional adjective or create artificial sale prices. Each price observation has a timestamp and source. Saved-product alerts use a configurable minimum percentage drop and per-product cooldown to suppress repeat notifications. Retailer price, stock, seller, delivery and return terms can change and should be rechecked on the retailer site.

## Image handling
- First choice: product image in retailer JSON-LD or Open Graph metadata.
- Secondary choice: search-result thumbnail.
- Fallback: a Brave image-search result matched to product title terms.
- The image source is recorded (retailer_page, search_thumbnail, or brave_image_search) so the UI can distinguish provenance. Visual similarity is not a guarantee of exact SKU identity.

## Automated refresh
A background asyncio scheduler checks only user-saved active searches. In live-provider mode it reruns due searches on the configured interval (default six hours). It is not a continuous internet crawler. Refresh requires the FIA backend process to remain running. Demo mode intentionally does not run automatic refresh.

## Persistence model
- ResearchJob: query lifecycle and status.
- Product: normalized canonical listing, latest observed offer, price-check timestamp, fashion attributes and optional GTIN/SKU identifiers. Exact GTIN matches expose separate retailer listings without combining seller or price data.
- ResearchResult: per-job product membership, relevance, trust and reasons.
- PriceObservation: immutable price snapshots when a changed price is observed.
- PriceAlert: price reductions that cross the saved minimum threshold, with read state and notification timestamp.
- SavedSearch: opt-in watchlist with active state and next refresh timestamp.
- SavedProduct: user's product shortlist.
- UserPreference: categories, brands, colours, sizes, notes and default budget.
- RetailerEvidence: domain-level provenance notes.

## Trust and safety boundary
The retailer-domain seed list only recognises exact official domains and their subdomains. It does not certify marketplace sellers. A secure connection or known marketplace domain does not prove that a particular seller, listing, product or offer is authentic. External page content is treated as untrusted data.

## Scaling path
The first release is intended for one local user and a single backend process. A later multi-user deployment should introduce authentication, per-user data isolation, durable background workers, network-layer egress controls, observability and a reviewed retailer connector policy.
