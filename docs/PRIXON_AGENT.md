# Prixon — Autonomous Windows Agent

Implementation record for Prixon_Autonomous_Agent_Plan(1).docx, version 1.0, dated 17 October 2026. This document is the scope authority for the prixon/ subsystem. FIA's fashion-research product remains separate.

## Runtime design

Two execution speeds share a local SQLite world model:

1. Reflex: normalize, classify by intent class, use hard negatives and owner corrections, route deterministic queries, ground slots, and apply risk-aware confidence. Common machine queries do not invoke the model.
2. Deliberate: optional local BGE/FastEmbed retrieval, schema-constrained Ollama arbitration over a grounded shortlist, and bounded planning for compound requests.

No hosted LLM fallback is configured. The Ollama client rejects non-loopback endpoints. Model output contains registered action identifiers and structured arguments; arbitrary shell, PowerShell, scripts and command strings are rejected by the validator/executor.

## Implemented components

| DOCX area | Implementation |
|---|---|
| L0 normalization / references | Text normalization, owner aliases, short-lived foreground/reference memory, clause splitting |
| L1 deterministic fast paths | CPU, RAM, battery, Wi-Fi, audio, network, process list and app-running queries; allowlisted app/window/volume/Settings actions |
| L2 semantic retrieval | Optional BGE-small FastEmbed adapter, top-8 retrieval, margin check, cosine deduplication and persisted owner examples |
| L3 grounding | Start Menu application catalogue, process/window index, fuzzy + embedding match, contextual aliases and stale-target checks |
| L4 arbitration | Local Ollama JSON-schema arbitration on a shortlist; low-confidence self-consistency check |
| L5 decision gate | Confidence fusion from retrieval, grounding, weak LLM confidence, context and user lexicon; tier-specific thresholds |
| Planning / execution | Typed plans, backward-only dependencies, required-slot/argument validation, max-step and wall-clock budgets, loop detection, timeouts, one retry for selected idempotent actions |
| Verification / undo | Native action postconditions, pre-action snapshots and SQLite undo journal for reversible actions; quarantine instead of permanent deletion |
| Autonomous loop | Persistent goals, WinEvent hooks, process delta observer, Downloads completion watcher, battery trigger, priority ordering and bounded polling |
| Governance | L0–L4 risk classes, per-minute action limit, proactive interruption limit, focus/fullscreen suppression, audit trail and kill switch |
| Learning | Beta-prior alias candidates, three-session promotion threshold, 0.85 promotion target, 0.5 demotion target, 60-day half-life, correction memory, entity aliases, delayed implicit-success window and owner reset |
| Consolidation | Successful-plan shape grouping, parameterized macro proposals and explicit approve/revoke |
| Evaluation | Frozen JSONL intent set, per-action metrics and confusion report; regression test gates |

## Windows 11 setup

Use Python 3.11+ and install the base application dependencies:

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,windows]"
~~~

Install Ollama separately and pull a small local model. The default is qwen2.5:3b-instruct. Set the following local environment options in .env (never commit tokens or credentials):

~~~dotenv
PRIXON_OLLAMA_BASE_URL=http://127.0.0.1:11434
PRIXON_OLLAMA_MODEL=qwen2.5:3b-instruct
PRIXON_OLLAMA_TIMEOUT_SECONDS=60
PRIXON_OLLAMA_KEEP_ALIVE=10m
PRIXON_AGENT_AUTOSTART=true
PRIXON_AGENT_MAX_PLAN_STEPS=8
PRIXON_AGENT_WALL_CLOCK_SECONDS=60
PRIXON_AGENT_STEP_TIMEOUT_SECONDS=12
PRIXON_AGENT_LOOP_POLL_SECONDS=2
PRIXON_SEMANTIC_ENABLED=false
~~~

For semantic retrieval, install the optional model dependency and enable it:

~~~powershell
pip install -e ".[semantic,windows,dev]"
$env:PRIXON_SEMANTIC_ENABLED="true"
~~~

FastEmbed downloads the selected embedding model the first time it is initialized. Embedding inference and subsequent retrieval are local. With semantic retrieval disabled or unavailable, the deterministic registry route remains active.

Start the FIA backend using the existing launcher:

~~~powershell
.\scripts\start-backend.ps1
~~~

On Windows, the backend starts the resident Prixon loop when PRIXON_AGENT_AUTOSTART=true. On non-Windows hosts the API remains importable for tests, but Windows actions and observers are unavailable.

## API

Base path: /api/v1/agent

| Method | Route | Purpose |
|---|---|---|
| GET | /health | Loop, Ollama, semantic and execution status |
| GET | /actions | Action registry including approved routines |
| POST | /decide | Preview a decision without executing |
| POST | /run | Plan/preview or execute one request |
| GET | /perception | Current bounded telemetry and indexed entities |
| POST | /plans/validate | Validate a plan without executing |
| GET/POST | /goals | Inspect/create explicit persistent goals |
| POST | /goals/{id}/status | Update/cancel a goal |
| POST | /runtime/start, /runtime/stop | Start/stop background observers and loop |
| POST | /kill | Trigger the shared kill switch |
| GET | /runtime/status | Loop, queue and kill-switch state |
| GET | /suggestions | Recent proactive suggestions |
| POST | /proactive/feedback | Accepted/dismissed suggestion feedback |
| POST | /undo/{undo_id} | Restore a journaled reversible action |
| POST | /aliases | Teach an action phrase alias after explicit confirmation |
| POST | /entities/aliases | Teach a confirmed entity alias with optional scope |
| GET | /learning | Inspect aliases, candidates, negatives and episode count |
| POST | /learning/feedback | Record owner feedback or correction |
| POST | /learning/consolidate | Run candidate decay/demotion |
| DELETE | /learning/aliases | Remove one learned alias/candidate |
| POST | /learning/reset | Confirmation-gated reset of learned state/macros |
| GET | /macros | Inspect proposed or approved macros |
| POST | /macros/{id}/approve | Approve or revoke a macro |
| POST | /macros/{id}/run | Preview/run an approved macro |
| GET | /audit, /events | Inspect audit records and pending event rows |
| POST | /governance/check | Evaluate the action's autonomy level |
| GET | /model/metrics | Last local inference request metrics |

Example preview:

~~~powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/agent/decide -ContentType "application/json" -Body '{"text":"show RAM usage"}'
~~~

Example explicit execution:

~~~powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/agent/run -ContentType "application/json" -Body '{"text":"open notepad","execute":true}'
~~~

An L4 action returns confirmation_required. Repeat the request with the exact intent and confirmed=true only after reviewing the proposed action. Do not treat /decide as execution.

## Safety boundaries

- All model endpoints are loopback-only HTTP. There is no cloud fallback.
- Only registry action IDs are callable; plan parameters must match the action schema. Arbitrary shell/PowerShell/script/command fields are rejected.
- Installed application launch targets must resolve to known Start Menu or Windows system roots.
- Credential/authentication window titles are redacted before they enter the world model; sensitive foreground contexts are excluded from window actions.
- State-changing actions capture prior state when an undo recipe exists. A quarantine action moves an explicitly supplied file inside the owner profile to a recoverable location; permanent file deletion is not provided.
- L4 actions (for example quarantine and window close) never run without explicit confirmation. Macro approval does not bypass an L4 member action.
- Action rate, plan length, wall clock, timeouts, kill switch and proactive interruptions are bounded.
- Proactive events create suggestions only; they do not autonomously launch, close or modify applications.
- Learning only uses owner requests and explicit owner feedback. Implicit success is queued and applied only after the 30-second correction/undo window.
- Owner learning is inspectable; individual entries can be removed and a confirmation-gated bulk reset is available.

## Evaluation

~~~powershell
ruff check fia prixon tests
pytest
python -m prixon.evaluation --dataset tests/data/prixon_eval.jsonl
~~~

The test corpus has a frozen regression subset and a growing subset. The report includes overall and per-action accuracy, clarification/unresolved counts, frozen accuracy and top confusions. A model-specific end-to-end benchmark must additionally record JSON-validity rate, p50/p95 latency, LLM-call share, token usage, wrong-execution rate and undo rate on the target Windows laptop.

## Current limitations / deliberate deferrals

- The Windows UI Automation (UIA) tree, keyboard/menu tier and vision/OCR fallback are not implemented; current actions use Win32, process APIs, Settings URIs and optional audio COM.
- Clipboard contents are not collected automatically; they can contain credentials and private text.
- The process observer reports process start/stop deltas; it does not yet distinguish a crash from a normal exit using ETW.
- File watching is scoped to the Downloads directory, not every user folder.
- Replanning with a different automation tier is not yet implemented. Selected idempotent actions receive one retry, then the failure is recorded and surfaced.
- Voice input and voice kill command, multilingual/code-mixed embeddings and LoRA are optional later work.
- Threshold fitting is available as an offline helper, but automated deployment is gated on a frozen-set non-regression review rather than enabled automatically.
- Windows-specific behavior must still be exercised on the target Windows 11 machine; Linux CI can validate pure-Python logic and API imports only.

These limitations are kept explicit rather than representing unimplemented adapters as complete.
