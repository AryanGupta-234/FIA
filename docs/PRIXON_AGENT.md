# Prixon — Autonomous Windows Agent

Implementation record for `Prixon_Autonomous_Agent_Plan(1).docx`, version 1.0, dated 17 October 2026. The DOCX is the scope authority for this subsystem. FIA's fashion-research workflow remains separate.

## Runtime design

Prixon uses a reflex path and a deliberate path over a shared local SQLite world model.

1. **L0 — Normalize and resolve references.** Normalize owner language, retain a short-lived foreground reference and expand confirmed owner aliases.
2. **L1 — Deterministic fast paths.** Classify by intent class and use typed action examples/hard negatives for common queries and fixed Windows actions. Common CPU, memory, battery, Wi-Fi, audio, network, process-list and app-running queries bypass Ollama.
3. **L2 — Semantic retrieval.** Optional local BGE/FastEmbed action retrieval returns a small shortlist with cosine ranking, deduplication and a margin requirement.
4. **L3 — Entity grounding.** Ground applications, processes, windows, known folders and recent files to observed local entities. Ambiguous or stale targets are not guessed.
5. **L4 — Constrained arbitration/planning.** Local Ollama receives only grounded action identifiers and bounded context, then returns schema-constrained JSON. Compound plans are typed data, not generated shell commands.
6. **L5 — Decision gate.** Deterministic confidence fusion and risk thresholds gate execution. LLM confidence has the weakest signal weight; L4 still requires explicit confirmation.

No hosted LLM fallback is configured. The Ollama client accepts only unauthenticated HTTP loopback endpoints. Perception and filesystem observers do not read page text, file contents, clipboard contents, credentials or password fields.

## Implemented components

| DOCX area | Branch implementation |
|---|---|
| Reflex / deliberate architecture | L0–L5 router foundations, typed registry, optional local embeddings, shortlist-only local Ollama and bounded compound planning |
| Look-alike handling | Intent-class filtering, hard negatives, owner correction penalties, candidate margins and clarification responses |
| Perception | Win32 foreground-window hook, process inventory/deltas, optional WMI non-zero process-exit detection, Start Menu apps and machine telemetry |
| World model / grounding | Persistent entity index for apps, processes, windows, known folders and bounded recent-file metadata; fuzzy and optional embedding match; scoped aliases |
| Semantic action retrieval | Optional BGE-small FastEmbed retrieval, top-8 shortlist, cosine deduplication, confidence margin and persisted reviewed examples |
| Confidence / decision | Retrieval margin, slot grounding, low-weight model confidence, context and owner lexicon; separate thresholds for read-only, reversible, allowlisted routine and always-confirm |
| Planning | Typed plan steps, required-slot and argument checks, backward-only dependencies, previous-step reference binding, bounded steps and loop detection |
| Action hierarchy | Native Win32/process/audio/Settings URI first; UI Automation and keyboard fallback for registered window actions; keyboard fallback verifies target foreground ownership |
| Execution / recovery | Per-step timeout, action rate limit, bounded retry for selected idempotent actions, postcondition verification, audit record and undo journal |
| Failure reflection | Structured likely-cause record; one single-step alternative replan only when a deterministic candidate is already grounded and its risk is no higher |
| Goal/event loop | Persistent goal queue, event persistence/replay, process/window/file/battery observers, local-time weekday routines and priority ordering |
| Proactive governance | Suggest-only notifications, cooldowns, annoyance/ignore state, per-hour interruption cap and focus/fullscreen suppression |
| Learning | Explicit teaching/correction, negative intent memory, 60-day evidence decay, delayed implicit-success window, promotion digest and owner approval/rejection API |
| Macros | Repeated successful plan-shape proposals, parameterized templates, explicit owner approval/revocation and L4 confirmation for member actions |
| Evaluation | 315 labeled utterance cases across clean/noisy/polite/pronoun/compound/look-alike/ambiguous/adversarial categories; frozen and growing splits; per-case/per-class reporting |

## Windows 11 setup

Use Python 3.11+.

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,windows]"
~~~

Install Ollama separately and pull a small local model. The default is `qwen2.5:3b-instruct`. Set these options in `.env` (do not commit secrets):

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

For semantic retrieval:

~~~powershell
pip install -e ".[semantic,windows,dev]"
$env:PRIXON_SEMANTIC_ENABLED="true"
~~~

FastEmbed downloads the selected embedding model the first time it initializes. Inference and subsequent retrieval are local. If semantic retrieval is disabled or unavailable, the deterministic registry route remains active.

Start the FIA backend using the existing PowerShell launcher:

~~~powershell
.\scripts\start-backend.ps1
~~~

On Windows 11, the backend starts the resident Prixon loop when `PRIXON_AGENT_AUTOSTART=true`. On non-Windows hosts, API imports and pure-Python tests are supported, but Windows actions and observers are unavailable.

## API

Base path: `/api/v1/agent`.

| Method | Route | Purpose |
|---|---|---|
| GET | `/health`, `/actions` | Runtime/model status and registered actions |
| POST | `/decide` | Preview a decision without executing |
| POST | `/run` | Preview or execute an owner request |
| GET | `/perception` | Bounded telemetry and locally indexed entities |
| POST | `/plans/validate` | Validate a plan without executing |
| GET/POST | `/goals` | Inspect/create persistent explicit goals |
| POST | `/goals/{id}/status` | Update or cancel a goal |
| POST | `/runtime/start`, `/runtime/stop` | Start/stop observers and agent loop |
| POST | `/kill` | Trigger shared kill switch |
| GET | `/runtime/status`, `/suggestions` | Loop state and proactive suggestions |
| POST | `/proactive/feedback` | Record accepted/dismissed suggestion feedback |
| POST | `/undo/{undo_id}` | Restore a journaled reversible action |
| POST | `/aliases`, `/entities/aliases` | Explicitly teach action/entity aliases |
| POST | `/learning/feedback` | Record owner feedback or a correction |
| GET | `/learning`, `/learning/digest` | Inspect candidates and review pending promotions |
| POST | `/learning/candidates/approve`, `/learning/candidates/reject` | Owner approval/rejection of implicit candidates |
| POST | `/learning/consolidate`, `/learning/reset` | Decay/demote candidates or reset learned state |
| DELETE | `/learning/aliases` | Remove one learned entry |
| GET | `/macros` | Inspect macro proposals/approved routines |
| POST | `/macros/{id}/approve`, `/macros/{id}/run` | Approve/revoke and preview/run an approved macro |
| GET/POST | `/routines` | List/create local weekday/time schedules for approved macros |
| POST/DELETE | `/routines/{id}/status`, `/routines/{id}` | Enable/disable/delete a schedule |
| GET | `/events`, `/audit` | Inspect pending events and audit history |
| POST | `/governance/check` | Evaluate an action's autonomy level |
| GET | `/model/metrics` | Inspect latest local inference metrics |

Example preview:

~~~powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/agent/decide -ContentType "application/json" -Body '{"text":"show RAM usage"}'
~~~

Example explicit execution:

~~~powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/agent/run -ContentType "application/json" -Body '{"text":"open notepad","execute":true}'
~~~

An L4 action returns `confirmation_required`. Review the proposed action and submit an explicit confirmation for that action. A preview endpoint never executes an action. Scheduled routine triggers create a suggestion; they do not auto-run the macro.

## Safety boundaries

- Model endpoint is local loopback only; there is no cloud provider fallback.
- Model output can select registered action IDs only. Unknown tools, unknown parameters, missing slots, invalid dependencies and unapproved command/script fields are rejected.
- Launch targets must resolve inside approved Start Menu or Windows system roots.
- Credential/authentication window titles are redacted before entering the world model; sensitive foreground contexts are excluded from window control.
- File observers read metadata only. They do not inspect content. They watch bounded known user folders (Downloads, Documents and Desktop).
- File quarantine requires an explicit path inside the user profile, and L4 confirmation; permanent deletion is not provided.
- L4 actions such as quarantine and window close always require confirmation. Macro approval does not bypass an L4 member action.
- A timed-out worker is not followed by another automation tier because it may still be running; this avoids concurrent duplicate state changes.
- Keyboard fallback runs only after validating the target HWND and confirming it became the foreground window. Vision/OCR clicking is not enabled.
- Action rate, plan length, wall clock, per-step timeout, loop retries and proactive interruptions are bounded.
- Proactive and scheduled-routine events produce suggestions only.
- Implicit learning is delayed to allow correction/undo. Candidates meeting the Beta-style confidence/session threshold are proposed in the owner digest; activation requires explicit owner approval.
- Owner can inspect, approve, reject, delete an entry or clear learned state.

## Evaluation

~~~powershell
ruff check fia prixon tests
pytest
python -m prixon.evaluation --dataset tests/data/prixon_eval.jsonl
~~~

The JSONL corpus currently contains 315 cases with frozen and growing partitions. Categories include clean, noisy, polite suffix, pronoun, compound, look-alike, ambiguous and adversarial inputs. The report includes overall and frozen accuracy, clarification/unresolved rate, deterministic L1 share, per-action, per-intent-class and per-case-type accuracy, plus top confusions.

The target-machine benchmark still needs to record p50/p95 end-to-end response time, JSON-validity rate, LLM-call share, token usage, wrong-execution rate, undo rate and Windows-host UIA behavior on the actual Windows 11 laptop. These are not marked passed by the pure-Python CI suite.

## Remaining limitations / validation

- Vision/OCR is not wired as an automation tier; it remains deferred until a visual action can be grounded and verified with strict safety gates.
- Clipboard content is not collected automatically.
- WMI process-stop classification is optional and depends on the optional Windows `pywin32` dependency; psutil still provides start/stop deltas.
- File metadata discovery is bounded to known user folders and a limited depth/count; the event watcher observes Downloads, Documents and Desktop, not the entire profile.
- Automatic failure replan currently applies only to a single-step action and only for a deterministically grounded same-or-lower-risk alternative. Compound-plan failures are surfaced instead of replaying already completed steps.
- The logistic calibration helper is offline only. Proposed weights are not automatically deployed; frozen wrong-execution non-regression still requires review.
- Voice input/voice kill command, multilingual/code-mixed model tuning and LoRA remain optional later work.
- Windows-specific UIA, WMI and keyboard behavior must still be exercised on the target Windows 11 machine; Linux CI covers pure-Python logic and API imports only.

Limitations are kept explicit rather than representing unimplemented adapters as complete.
