# Prixon Agent — implementation status

This document tracks the implementation of the Prixon autonomous Windows-agent plan. FIA's fashion research workflow remains separate.

## Implemented

### Semantic intent
- L0 normalization, owner aliases and short-lived reference resolution.
- L1 deterministic environment/control routing.
- L2 optional local FastEmbed/BGE retrieval and retrieval margins.
- L3 grounding against installed applications, processes and windows.
- Context-scoped entity aliases and corrected-intent negative memory.
- L4 constrained local Ollama arbitration on grounded candidates.
- Low-confidence self-consistency; disagreement escalates.
- L5 deterministic confidence fusion and risk-tier decision gating.

### Autonomous loop
- Persistent SQLite world/goal/episode/alias/macro/undo/audit state, with bounded privacy-filtered world-state history.
- WinEvent foreground/window events, process deltas and Downloads completion events.
- Explicit clipboard metadata and confirmation-gated text reads; clipboard text is excluded from persistent audit/episode records.
- Explicit-goal continuation and local owner context (time/day/routine state).
- Global Ctrl+Alt+Pause kill switch, plus opt-in Ctrl+Alt+V push-to-listen voice kill.
- Rules-first proactive candidate engine; only event candidates are passed to constrained local-model worthiness judgement. Model can veto/refine one suggestion but cannot select tools or act. Focus/fullscreen suppression, cooldowns and persistent annoyance remain deterministic.

### Safe execution
- Typed action contracts with slots, preconditions, postconditions, undo support, risk, per-action timeouts, idempotency, retry policy and automation tiers.
- Plan validation at planner and executor boundaries.
- Native Win32/Settings URI adapters plus tier-2 Windows media-session and Office COM adapters; media reads playback state only, Office reads open/unsaved counts only.
- Optional loopback Chromium DevTools diagnostics for browser product/version and target-type counts only; no URLs, titles, DOM, cookies or page data are read.
- UI Automation summaries are bounded to actionable roles/names/automation IDs, cached per HWND, and invalidated on window lifecycle/focus events.
- Step, wall-clock, model-token and action-rate budgets. Each action declares its own timeout, idempotency and retry policy within the global step limit. Ollama generation tokens are charged against one per-request budget shared by arbitration, self-consistency, compound planning and failure reflection; partial compound recovery inherits the original wall-clock deadline.
- Postcondition verification and deterministic prediction-error logging.
- Retry once, then constrained failure reflection/replan, then escalation.
- Compound failure recovery resumes only independent unattempted steps; completed actions are never replayed and dependent steps are surfaced as blocked.
- Undo journal and quarantine for user-profile file moves.
- Append-only audit records, nightly JSONL archive rotation, an archive index/download API and one-click active-log export.

### Learning
- Multi-session success/failure evidence with decay.
- Explicit owner teaching, direct clarification-answer learning and correction-driven negative memory.
- Multiple action and entity meanings can coexist under foreground-app, time-of-day, weekday or hour scopes; the most specific matching scope wins.
- Context-scoped entity aliases are grounded against live entities before use.
- Nightly consolidation and repeated plan-shape macro proposals.
- Approved macros become registry actions.

### Clarification-answer API

Use `POST /api/v1/agent/learning/clarification-answer` when the owner answers a Prixon clarification. Supply either `action_name` or both `entity_type` and `target`, plus an optional scope. The direct owner answer is treated as explicit teaching; observed screen, file, page or tool output is never used as a teaching signal.

### Evaluation/performance
- Frozen + growing JSONL intent benchmark, including wrong-selection rate separately from safe abstention.
- Versioned 12,840-example global seed corpus generated from registered action examples, loaded through chunked BGE embeddings and cached in SQLite by model/corpus version.
- Offline confidence-weight fitting.
- Prompt/response size, latency, load-duration, keep-alive, lifetime success/failure, malformed-JSON and JSON-validity metrics, plus rolling p50/p95 summaries.
- Preview-only target-machine benchmark CLI for end-to-end latency, LLM-call share and token measurements.

## Multilingual and code-mixed evaluation

A separate 40-case Hindi/Hinglish/Devanagari evaluation corpus is stored at `tests/data/prixon_multilingual_eval.jsonl`. It is intentionally separate from the English frozen/growing benchmark.

To measure it with local multilingual embeddings:

~~~powershell
$env:PRIXON_SEMANTIC_ENABLED="true"
$env:PRIXON_SEMANTIC_MODEL_NAME="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
py -3.11 -m pip install -e ".[semantic]"
py -3.11 -m prixon.benchmark --dataset tests/data/prixon_multilingual_eval.jsonl --output artifacts/prixon-multilingual-v1.json
~~~

The model name is configurable because multilingual embeddings are an experiment, not the default laptop profile. Compare the report against the default BGE model before promoting a model or threshold. The evaluation corpus never trains or updates the model.

## Target-machine benchmark

Run from the repository root on the Windows device with Prixon configured and the local Ollama model already pulled:

~~~powershell
py -3.11 -m pip install -e ".[dev,windows,media,browser]"
py -3.11 -m prixon.benchmark --split all --output artifacts/prixon-benchmark-latest.json
~~~

This benchmark calls the preview/decision path only; it does not execute Windows actions. It archives end-to-end p50/p95 latency, wrong-selection and clarification rates, local-model request share, call count, JSON-validity rate and Ollama token totals. Run it separately for `--split frozen` and `--split growing` when comparing a routing or confidence-policy change. Hardware results must be measured on the target laptop; CI results are not a substitute.

## Safety boundaries
- Ollama endpoint is loopback-only; there is no hosted-model fallback.
- Credential/authentication-like window titles are redacted from world context.
- L4 actions never execute autonomously.
- Observed window/page/file text cannot teach aliases or elevate autonomy.
- No browser credentials, cookies or password fields are collected.
- Clipboard text is fetched only for a direct owner request after L4 confirmation; it is returned to the requester but never written to audit, episode or persistent goal records. Sensitive clipboard actions are blocked from background goals and macro promotion.
- Vision/OCR remains a future last-resort tier; Browser DevTools is metadata-only and never used to scrape or interpret page content.

## Windows media controls (tier 2)

Media actions use the Windows Global System Media Transport Controls session API. The adapter requests only the playback state and app user-model id; it deliberately does not request track title, artist, album, browser URLs or page content.

Install the optional package with:

~~~powershell
py -3.11 -m pip install -e ".[windows,media]"
~~~

Available actions include `media.status`, `media.play`, `media.pause`, `media.stop`, `media.skip_next` and `media.skip_previous`. A target app can be supplied when an active media session for that app exists; otherwise Prixon uses the Windows current media session.

## Office session metadata (tier 2)

The Office COM adapter reports whether Word, Excel and PowerPoint sessions are active, plus open-item and unsaved-item counts. It never reads document/workbook/presentation names, paths, text, cells, formulas, slide content or selection values. It uses the existing optional `.[windows]` dependencies.

The action is `office.status`.

## Chromium debugging metadata (tier 2)

Browser diagnostics are disabled by default. To opt in, close the browser and start Brave, Chrome or Edge yourself with a loopback-only debugging port, for example:

~~~powershell
& "$env:ProgramFiles\BraveSoftware\Brave-Browser\Application\brave.exe" --remote-debugging-port=9222
~~~

Then set `PRIXON_BROWSER_DEBUG_ENABLED=true` in `.env`. Install the optional websocket dependency:

~~~powershell
py -3.11 -m pip install -e ".[windows,browser]"
~~~

The `browser.debug_status` action only calls Chromium's local browser/version and target-list diagnostics and returns the product/version plus counts by target type. It discards target URLs and titles and does not inspect page contents, cookies, storage, DOM, form values or browser history. The endpoint is required to be loopback and match the configured port; non-local websocket destinations are rejected. Disable the adapter with `PRIXON_BROWSER_DEBUG_ENABLED=false`.

## Optional local voice kill

Voice kill is opt-in and uses a local Vosk model. It does not keep the microphone open. Press `Ctrl+Alt+V`, then say **“Prixon stop”** within the short capture window. Only fixed stop/halt/abort phrases are accepted.

~~~powershell
./scripts/setup-prixon-voice.ps1
~~~

The setup script installs the optional Vosk and sounddevice packages, downloads the small English model, writes its local path into `.env`, and enables voice kill. Disable it with `PRIXON_VOICE_KILL_ENABLED=false`. Status is available at `GET /api/v1/agent/voice/status`.

## API
Agent routes are mounted under `/api/v1/agent`.

Core routes:
- `GET /health`
- `GET /actions`
- `POST /decide`
- `POST /run`
- `POST /goals`
- `POST /runtime/start`
- `POST /runtime/stop`
- `POST /kill`
- `GET /voice/status`
- `GET /audit`, `GET /audit/export`, `GET /audit/archives`, `GET /audit/archives/{filename}`
- `GET /world-state`
- `POST /undo/{id}`
- `GET /macros`
- learning and proactive feedback routes

## Windows prototype setup

From the repository root in PowerShell:

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[windows,media,browser,voice]"
Copy-Item .env.example .env -ErrorAction SilentlyContinue
.\scripts\open-prixon.ps1
~~~

The UI opens at `http://127.0.0.1:8000/api/v1/agent/ui` unless `API_PORT` is changed in `.env`.

To launch Prixon automatically at Windows sign-in, run:

~~~powershell
.\scripts\install-prixon-startup.ps1
~~~

Remove automatic startup with `.scripts\uninstall-prixon-startup.ps1`. Server logs are written under `%LOCALAPPDATA%\Prixon\logs`. The task runs as the signed-in user without administrator elevation or a stored password.

Semantic retrieval is optional. Install `.[semantic]` separately and set `PRIXON_SEMANTIC_ENABLED=true` only when you want to load the local BGE model.

## Run

~~~powershell
py -3.11 -m pip install -e ".[dev,windows]"
$env:PRIXON_SEMANTIC_ENABLED="true"  # optional; installs FastEmbed separately
py -3.11 -m pytest
~~~
