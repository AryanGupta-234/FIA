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
- Owner-confirmed L3 routine execution for safe approved macros, with durable once-per-date claims, inspectable run history and no blind replay after interruption.
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

### Owner-reviewed confidence calibration

Recent decisions can be reviewed in the Learning panel or with `GET /api/v1/agent/decisions/review`. Mark an interpretation correct/incorrect only after comparing it with the original owner request; technical action completion alone is not a correctness label.

After at least 20 owner-reviewed selected decisions, generate an inactive proposal with `POST /api/v1/agent/calibration/propose` or run:

~~~powershell
py -3.11 -m prixon.calibration --output artifacts/prixon-calibration-proposal.json
~~~

The proposal fits non-negative logistic weights and per-risk cutoffs from owner labels. It never activates itself. Activation through `POST /api/v1/agent/calibration/apply` requires owner confirmation, a frozen-regression comparison with no accuracy loss, and a measured wrong-execution rate at or below the proposal target. L4 remains always-confirm.

### Evaluation/performance
- Frozen + growing JSONL intent benchmark, including wrong-selection rate separately from safe abstention.
- Versioned 12,840-example global seed corpus generated from registered action examples, loaded through chunked BGE embeddings and cached in SQLite by model/corpus version.
- Offline confidence-weight fitting.
- Decision traces correlate confidence-signal records with final execution/verification outcomes, including blocked, preview-only, confirmation-required and compound-step outcomes.
- Per-layer latency and LLM-call counts are captured by preview; the deferred target-machine benchmark reports p50/p95 per layer and end-to-end.
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

This benchmark calls the preview/decision path only; it does not execute Windows actions. It archives end-to-end and per-layer p50/p95 latency, wrong-selection and clarification rates, local-model request share, call count, JSON-validity rate and Ollama token totals. Run it separately for `--split frozen` and `--split growing` when comparing a routing or confidence-policy change. Hardware results must be measured on the target laptop; CI results are not a substitute.

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

## Optional local push-to-talk voice

Voice remains opt-in. The microphone is not continuously open: the local Vosk listener is activated only after a hotkey. The optional setup installs Vosk/sounddevice and a local English speech model, then enables two separate hotkeys:

- `Ctrl+Alt+V`: short constrained emergency-stop phrase capture (for example, “Prixon stop”).
- `Ctrl+Alt+M`: finite local speech-to-text capture for ordinary commands; the recognized request goes through the same owner-request routing, confidence/risk gates, confirmation and audit path as typed input.

Raw audio is processed in memory and discarded; no cloud speech service is used. Recognized transcripts are not returned by the voice-command history endpoint. The voice setup script enables the optional local commands and kill path; it does not enable voice at Windows sign-in if the user has not installed/started Prixon.

~~~powershell
./scripts/setup-prixon-voice.ps1
~~~

Restart Prixon after the setup. Status is available at `GET /api/v1/agent/voice/status`; bounded in-memory command outcomes are available at `GET /api/v1/agent/voice/commands`. Set PRIXON_VOICE_KILL_ENABLED=false and PRIXON_VOICE_COMMANDS_ENABLED=false in the local .env file to disable both listeners.

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
- `GET /voice/status`, `GET /voice/commands`
- `GET /audit`, `GET /audit/export`, `GET /audit/archives`, `GET /audit/archives/{filename}`
- `GET /world-state`
- `POST /undo/{id}`
- `GET /macros`
- learning and proactive feedback routes
- `GET /decisions/review`, `POST /decision-feedback`, `POST /calibration/propose`, `GET /calibration/proposal`, `POST /calibration/apply`
- `GET /routines`, `POST /routines`, `GET /routine-runs`

## Windows prototype setup

From the repository root in PowerShell:

~~~powershell
.\scripts\setup-prixon.ps1
.\scripts\open-prixon.ps1
~~~

The setup script creates the local virtual environment and installs the Windows, media and browser adapters. Voice remains opt-in; run `./scripts/setup-prixon-voice.ps1` only when you want local push-to-listen speech.

The UI opens at `http://127.0.0.1:8000/api/v1/agent/ui` unless `API_PORT` is changed in `.env`.

To add a Start Menu shortcut, run `./scripts/install-prixon-startmenu.ps1`.

To launch Prixon automatically at Windows sign-in, run:

~~~powershell
.\scripts\install-prixon-startup.ps1
~~~

Remove automatic startup with `./scripts/uninstall-prixon-startup.ps1`. Server logs are written under `%LOCALAPPDATA%\Prixon\logs`. The task runs as the signed-in user without administrator elevation or a stored password.

Semantic retrieval is optional. Install `.[semantic]` separately and set `PRIXON_SEMANTIC_ENABLED=true` only when you want to load the local BGE model.

## Run

~~~powershell
py -3.11 -m pip install -e ".[dev,windows]"
$env:PRIXON_SEMANTIC_ENABLED="true"  # optional; installs FastEmbed separately
py -3.11 -m pytest
~~~
