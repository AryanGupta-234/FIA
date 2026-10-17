# FIA Roadmap

## v0.2 — Research workspace
- [x] Remove Docker-based setup; Windows-first PowerShell launch
- [x] First-run boot screen and Windows Start Menu shortcut installer
- [x] Responsive research dashboard, offer radar, saved items and history
- [x] Brave India web discovery and image search fallback
- [x] Retailer JSON-LD Product/Offer extraction
- [x] Discount evidence and price-change observations
- [x] Opt-in saved-search refresh scheduler
- [x] Research result provenance and seller/domain evidence
- [x] Additive local SQLite column migration

## v0.3 — Better offer coverage
- [ ] Additional retailer-approved product feeds and affiliate/catalog APIs
- [ ] Coupon validity and shipping/return detail adapters
- [ ] Seller-level marketplace evidence where the source exposes seller IDs
- [x] In-app price-drop alerts for saved products when a lower same-currency price is observed
- [x] Price freshness timestamps, stale badges, fresh-only offer feed and configurable alert thresholds
- [x] Exact validated GTIN matching across retailer listings (preserving independent offers and sellers)

## v0.4 — Fashion intelligence
- [ ] Feedback-driven personal ranking
- [x] Structured fit, material, colour, size, product type and audience extraction
- [ ] Image embeddings for visually similar products
- [ ] Outfit compatibility and wardrobe planning
- [ ] Multilingual Indian query expansion

## v1.0 — Reliable personal agent
- [ ] Durable worker queue with retries
- [ ] Authentication and multi-user isolation
- [ ] Network egress gateway and formal security review
- [ ] Observability, retention controls and backup/restore
- [ ] Accessibility, performance and deployment hardening

FIA remains research-only. Purchase and checkout automation are intentionally out of scope.


## Prixon — autonomous Windows agent (parallel subsystem)

### P0 — Foundation
- [x] Isolated `prixon/` package and API router
- [x] Rules-first intent router and typed action registry
- [x] Plan schema and deterministic validation
- [x] L0-L4 risk decision helper
- [x] Local-only Ollama adapter and health check
- [x] Initial regression tests

### P1 — Perception and grounding
- [ ] Windows process/window perception adapter
- [ ] Installed application entity catalogue
- [ ] Foreground-window context and short-lived reference resolver
- [ ] Normalized status queries that bypass the LLM

### P2 — Semantic understanding
- [ ] Embedding index, retrieval margin and hard negatives
- [ ] Frozen evaluation dataset and calibrated confidence fusion
- [ ] Constrained Ollama arbitration on grounded shortlist

### P3 — Safe execution
- [ ] Plan preconditions and execution budgets
- [ ] Windows allowlisted adapters, observable verification and retries
- [ ] Undo journal, append-only audit and kill switch

### P4 — Learning and autonomy
- [ ] Owner-only synonym/alias learning with Beta confidence and decay
- [ ] Goal stack, event bus and bounded proactive suggestions
- [ ] Macro promotion and offline threshold tuning
