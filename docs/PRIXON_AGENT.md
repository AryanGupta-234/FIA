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
- Persistent SQLite world/goal/episode/alias/macro/undo/audit state.
- WinEvent foreground/window events, process deltas and Downloads completion events.
- Explicit-goal continuation and local owner context (time/day/routine state).
- Global Ctrl+Alt+Pause kill switch.
- Suggest-only proactive engine with cooldown, focus/fullscreen suppression and persistent annoyance.

### Safe execution
- Typed action contracts with slots, preconditions, postconditions, undo support, risk and automation tiers.
- Plan validation at planner and executor boundaries.
- Native Windows adapters without model-generated shell/script/PowerShell.
- Step, wall-clock, model-token and action-rate budgets, with the same wall-clock deadline across partial recovery.
- Postcondition verification and deterministic prediction-error logging.
- Retry once, then constrained failure reflection/replan, then escalation.
- Compound failure recovery resumes only independent unattempted steps; completed actions are never replayed and dependent steps are surfaced as blocked.
- Undo journal and quarantine for user-profile file moves.
- Append-only audit records.

### Learning
- Multi-session success/failure evidence with decay.
- Explicit owner teaching and correction-driven negative memory.
- Context-scoped entity aliases.
- Nightly consolidation and repeated plan-shape macro proposals.
- Approved macros become registry actions.

### Evaluation/performance
- Frozen + growing JSONL intent benchmark, including wrong-selection rate separately from safe abstention.
- Offline confidence-weight fitting.
- Prompt/response size, latency, load-duration and keep-alive logging with rolling p50/p95 summaries; failed Ollama attempts are included in call and latency metrics.
- Preview-only target-machine benchmark CLI for end-to-end latency, LLM-call share and token measurements.

## Target-machine benchmark

Run from the repository root on the Windows device with Prixon configured and the local Ollama model already pulled:

~~~powershell
py -3.11 -m pip install -e ".[dev,windows]"
py -3.11 -m prixon.benchmark --split all --output artifacts/prixon-benchmark-latest.json
~~~

This benchmark calls the preview/decision path only; it does not execute Windows actions. It archives end-to-end p50/p95 latency, wrong-selection and clarification rates, local-model request share, call count and Ollama token totals. Run it separately for `--split frozen` and `--split growing` when comparing a routing or confidence-policy change. Hardware results must be measured on the target laptop; CI results are not a substitute.

## Safety boundaries
- Ollama endpoint is loopback-only; there is no hosted-model fallback.
- Credential/authentication-like window titles are redacted from world context.
- L4 actions never execute autonomously.
- Observed window/page/file text cannot teach aliases or elevate autonomy.
- No browser credentials, cookies or password fields are collected.
- Vision/OCR and app-specific adapters remain future automation tiers.

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
- `GET /audit`
- `POST /undo/{id}`
- `GET /macros`
- learning and proactive feedback routes

## Run

~~~powershell
py -3.11 -m pip install -e ".[dev,windows]"
$env:PRIXON_SEMANTIC_ENABLED="true"  # optional; installs FastEmbed separately
py -3.11 -m pytest
~~~
