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


### Prixon — DOCX implementation roadmap

#### Phase 0 — Local model and inference instrumentation
- [x] Loopback-only Ollama endpoint; no cloud fallback
- [x] Request/response size, model, endpoint, keep-alive and latency metrics
- [ ] Validate decision-call p50/p95 on the target Windows laptop and tune for a few-second response

#### Phase 1 — Registry and hard-negative retrieval
- [x] Typed contracts with verb, target, parameters, pre/postconditions, risk and automation tiers
- [x] Intent-class filtering, contrastive examples, hard negatives and owner correction penalties
- [x] No TF-IDF path
- [x] Expand examples for status/settings/window/app-running look-alikes

#### Phase 2 — Perception and grounding
- [x] Process/window observation, Start Menu application catalogue, foreground context and short-lived references
- [x] Deterministic CPU, RAM, battery, Wi-Fi, audio, network and process queries
- [x] Fuzzy and contextual entity index; recent-file metadata from bounded known folders
- [x] File change observation in Downloads, Documents and Desktop
- [x] Optional WMI non-zero process-exit/crash classification
- [ ] Add clipboard perception only behind explicit, privacy-reviewed actions

#### Phase 3 — Retrieval and decision gate
- [x] Optional BGE/FastEmbed action retrieval with top-8 shortlist and rank margin
- [x] Entity embedding/fuzzy grounding and owner example persistence
- [x] Confidence fusion and risk-tier thresholds; weak LLM-confidence weight
- [x] 315-case frozen/growing labelled JSONL corpus with per-action, per-class and per-category reports
- [ ] Run and archive the target-machine benchmark; wrong-execution target must be agreed before deployment

#### Phase 4 — Constrained local arbitration
- [x] JSON-schema Ollama arbitration over grounded candidates only
- [x] Two-sample low-confidence disagreement clarification
- [x] Recent successful episodes supplied as short few-shot context
- [x] Structured failure reflection and a bounded single-step same-or-lower-risk replan
- [ ] Measure JSON validity and LLM-call share on real owner traffic

#### Phase 5 — Planning, execution and verification
- [x] Compound clause retrieval, typed plan schema, dependency validation and bounded steps
- [x] Allowlisted Win32, process, audio and Settings URI adapters
- [x] UI Automation and keyboard fallbacks for registered window actions
- [x] Pre-action capture, timeouts, rate limits, postconditions, retry-once and undo journal
- [x] Quarantine instead of permanent deletion; L4 confirmation
- [ ] Compound-plan recovery/replanning after a partial execution; current behavior safely surfaces the partial result

#### Phase 6 — Persistent autonomy loop and governance
- [x] Persistent goal stack, event bus, WinEvent hooks, process/file/battery observers and audit records
- [x] Local-time weekday routine schedules; schedule triggers remain suggestion-only
- [x] Priority ordering, wall-clock/step/action budgets and loop abort
- [x] Global Ctrl+Alt+Pause kill switch
- [x] Proactive suggestions are suppressed in focus/fullscreen and are suggestion-only
- [ ] Add voice kill command

#### Phase 7 — Evolving language and owner learning
- [x] Explicit alias teaching, corrections, negative memory and contextual entity aliases
- [x] Beta-prior confidence, multi-session promotion candidates, demotion and 60-day half-life
- [x] Delayed weak success signal; correction/undo window; owner inspect/delete/reset controls
- [x] Nightly learning digest with confirmation-gated approve/reject API
- [x] Incremental, persistent embedding example growth with cosine deduplication/cap

#### Phase 8 — Proactivity, macros and calibration
- [x] Trigger cooldowns, annoyance score, accepted/dismissed feedback and interruption cap
- [x] Repeated plan-shape grouping, parameterized macro proposals and explicit approval/revocation
- [x] Offline logistic confidence-weight fitting helper
- [ ] Compare frozen-set wrong-execution before/after; only then deploy calibrated weights/thresholds

#### Phase 9 — Optional research extensions
- [ ] LoRA using only reviewed labels and frozen-set evidence
- [ ] Multilingual/code-mixed embedding evaluation
- [ ] Voice-first interaction and UI polish
