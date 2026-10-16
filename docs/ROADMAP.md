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
