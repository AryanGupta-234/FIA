# FIA — Fashion Intelligence Agent

An India-first fashion research workspace. Describe what you want, and FIA searches configured discovery sources, inspects permitted product pages, extracts structured product/offer data, captures images, compares evidence and keeps an opt-in watchlist refreshed.

**FIA is research-only.** It never logs in to stores, adds products to carts, checks out or purchases anything.

## What is included
- FastAPI + SQLAlchemy backend; SQLite by default.
- India-scoped Brave Search integration for web listings and image search.
- Product-page extraction for JSON-LD Product/Offer, images, prices, availability, seller details and fashion attributes (colour, material, fit, size and audience).
- Offer evidence: current/original price, discount percentage and timestamped price observations when exposed by the source.
- In-app price-drop alerts for saved products when a later refresh confirms a same-currency reduction above your configured threshold; duplicate alerts are cooled down.
- Price freshness labels; offer feeds exclude prices older than the configured freshness window by default.
- Exact validated GTIN matching across retailer listings, without merging separate seller prices or product records.
- Retailer-domain evidence with transparent reasons and no blanket authenticity claims.
- Research history, saved products, style preferences and opt-in saved-search monitoring.
- React + Vite workspace with an animated first-run boot screen, dashboard, discover, offers, saved pieces and history views.
- Windows PowerShell launcher plus optional Windows Start Menu shortcut.

## Windows 11 setup
Requirements: Python 3.11+ and Node.js 20+.

1. Clone the repository and switch to dev.
2. Copy .env.example to .env.
3. For live discovery, set SEARCH_PROVIDER=brave and add your own BRAVE_SEARCH_API_KEY in .env. Without a key, FIA runs in clearly labelled demo mode.
4. Start everything with ./scripts/start-fia.ps1.
5. Open http://localhost:5173. API docs are at http://127.0.0.1:8000/docs.

To add FIA to the Windows Start Menu, run ./scripts/install-start-menu.ps1 once. Search Start for FIA - Fashion Intelligence Agent.

For manual launch, use ./scripts/start-backend.ps1 and ./scripts/start-dashboard.ps1 in separate PowerShell windows.

## Live discovery configuration
See .env.example. The Brave API key is supplied by the user and must not be committed. The web and image endpoints are separate. Automatic refresh runs only for active saved searches and only while the backend is running with a live provider. Default cadence: six hours. Prices are labelled stale after 72 hours by default; the freshness window, alert cooldown and fallback alert threshold can be changed in `.env`. The alert threshold can also be set in the Style Profile.

## API surface
- GET /api/v1/health
- POST /api/v1/research and GET /api/v1/research/{job_id}
- GET /api/v1/products, GET /api/v1/products/{product_id}, GET /api/v1/products/{product_id}/matches
- GET /api/v1/offers (use `include_stale=true` to include expired observations), GET /api/v1/history
- GET /api/v1/alerts, POST /api/v1/alerts/{id}/read
- GET/POST /api/v1/saved-searches, PUT/DELETE /api/v1/saved-searches/{id}
- POST /api/v1/saved-searches/{id}/refresh
- GET /api/v1/saved-products, POST/DELETE /api/v1/saved-products/{product_id}
- GET/PUT /api/v1/preferences, GET /api/v1/retailers, GET /api/v1/stats

## Development
Python:
~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
ruff check fia tests
pytest
~~~

Dashboard:
~~~powershell
cd frontend
npm install
npm run build
~~~

## Accuracy boundaries
FIA cannot crawl the entire internet exhaustively. Coverage depends on the configured search provider, the results it returns, retailer permissions and robots policy. Images from image search are a fallback and may not represent the exact SKU. A visible discount is shown only when source data provides the relevant price evidence. Always verify the live retailer listing before purchase.

See docs/ARCHITECTURE.md, docs/SECURITY.md and docs/ROADMAP.md.
