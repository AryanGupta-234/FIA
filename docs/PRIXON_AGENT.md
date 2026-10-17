# Prixon Agent — implementation notes

Prixon is a local-first Windows agent subsystem developed alongside FIA. FIA's fashion discovery workflow remains separate and research-only. The Prixon design is based on the implementation plan dated 17 October 2026.

## Current slice

- Rules-first intent classification and allowlisted action retrieval.
- Typed action contracts with intent class, target type, required slots, risk tier and postconditions.
- Plan schema validation: known tools, backward-only dependencies and step budget.
- L0-L4 governance decision helper.
- Local-only Ollama health/client adapter. No cloud model fallback.
- API endpoints under `/api/v1/agent`.
- No Windows actions are executed yet. Decision preview is deliberately separate from execution.

## Architecture direction

The implementation follows the design's reflex/deliberate split. Deterministic rules and registry matching run first. Future embedding retrieval will produce a short candidate list. Ollama will be invoked only for ambiguous, grounded candidates or compound planning; generated output must validate against schemas and the registry.

## Safety invariants

1. Model output selects registered action identifiers only; it never supplies arbitrary shell commands.
2. Perception/page/file text is untrusted data, not instructions.
3. Read-only and reversible actions are separate from always-confirm operations.
4. Destructive file actions must use quarantine and an undo journal, never permanent deletion.
5. Every real action will require preconditions, timeouts, observable postconditions and audit records.
6. Ollama is local-only; missing Ollama does not trigger a hosted provider fallback.
7. Credential dialogs, password fields and secrets are out of scope.

## API

- `GET /api/v1/agent/health`
- `GET /api/v1/agent/actions`
- `POST /api/v1/agent/decide` with `{"text":"show system health"}`
- `POST /api/v1/agent/aliases` with explicit `confirmed: true`
- `POST /api/v1/agent/governance/check`

## Run tests

```powershell
py -3.11 -m pip install -e ".[dev]"
py -3.11 -m pytest tests/test_prixon_agent.py
```

## Next increments

1. Windows perception adapters (foreground window, process inventory, installed application catalogue).
2. Entity grounding and short-lived reference memory.
3. Semantic example retrieval with margin and hard-negative eval set.
4. Decision confidence fusion calibrated on a frozen test set.
5. Executor, verifier, undo journal, event bus, kill switch and audit log.
6. Owner-only synonym learning with Beta confidence and decay.
