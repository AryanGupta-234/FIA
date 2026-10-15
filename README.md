# Fashion Intelligence Agent (FIA)

Standalone India-first fashion product research assistant. FIA discovers products from configured search providers and permitted retailer pages, normalizes listings, records provenance, ranks relevance and presents evidence-backed comparisons.

**Research-only autonomy:** no store login, cart actions, checkout, payment or purchasing.

## Features
- FastAPI backend and SQLAlchemy persistence (SQLite by default; PostgreSQL supported).
- Pluggable asynchronous search providers: local demo and optional Brave Search.
- Robots-aware page fetching with timeout, response-size and content-type limits.
- JSON-LD Product/Offer extraction and metadata fallback.
- URL normalization, deduplication, budget-aware ranking and explainable retailer-domain evidence.
- Research history, product records, price observations and user preferences.
- React + Vite dashboard.
- Windows PowerShell launch scripts, Dockerfile, Compose and GitHub Actions CI.

## Windows 11 quick start
1. Install Python 3.11+ and Node.js 20+.
2. Copy `.env.example` to `.env`.
3. Run `./scripts/start-backend.ps1` in PowerShell.
4. Run `./scripts/start-dashboard.ps1` in another terminal.
5. Open http://localhost:5173 (API docs: http://localhost:8000/docs).

Without API credentials FIA runs in clearly-labelled demo mode. Configure `BRAVE_SEARCH_API_KEY` and `SEARCH_PROVIDER=brave` in `.env` for live search.

## API
- `GET /api/v1/health`
- `POST /api/v1/research`
- `GET /api/v1/research/{job_id}`
- `GET /api/v1/products`
- `GET /api/v1/retailers`
- `GET|PUT /api/v1/preferences`
- `GET /api/v1/stats`

## Development
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
ruff check .
cd frontend
npm install
npm run build
```

See `docs/ARCHITECTURE.md`, `docs/SECURITY.md` and `docs/ROADMAP.md`. Search coverage is limited by provider availability and retailer permissions; it is not exhaustive internet crawling. Always verify live price, stock, seller, size, delivery and returns on the retailer website.