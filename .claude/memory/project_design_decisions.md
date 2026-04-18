---
name: Core Design Decisions
description: Key non-obvious design decisions for context mechanism, error management, and reporter — choices that aren't self-evident from code
type: project
originSessionId: 88b1a5d4-a9c9-4ecc-9e65-eeee32f178a8
---
## Context Mechanism (2026-04-17)

- Removed `cache` field — all params/series auto-injected into context
- Removed `expr` (eval-based) — replaced by `call` with FunctionManager (builtin + external)
- Context keys use dot notation: `{sid}.sim`, `{sid}.obs` (not underscore)
- `P` (physical params vector) auto-injected after write_params, no manual cache needed
- `call` args changed from dict to list (positional matching)
- Builtin functions: `kind: builtin` skips args validation; `kind: external` requires declared args

**Why:** cache was confusing (sounded like performance), expr had eval() security issues, dot notation freed keys from Python variable name rules.

## Error Management (2026-04-17)

- RunError has `severity` field: "fatal" / "warning"
- Warning collection via `context["warnings"]` list, not exception control flow
- Fatal vs warning rules:
  - objective/constraint failure → fatal (abort run)
  - diagnostic failure → warning (fill on_error, continue)
  - derived failure → check `fatalDerivedIds` set (built at init by tracing objective/constraint dependency chains)
- on_error defaults: objective min→+inf, max→-inf; constraint→+inf; diagnostic→NaN
- Clamp warnings aggregated per-param: one warning per param with count of affected files

## Reporter (2026-04-17)

- Summary table: DB + CSV unified columns, order: identifiers → status → eval results → X_ params → P_ params
- Series storage: DB keeps BLOB (float32), CSV export is optional wide-table per series (sim only)
- Errors table: unified error+warning, severity field distinguishes them
- External logs: error.jsonl (machine) + error.log (human), both contain error+warning
- Holding pen: flush on threshold, slow runs appended later (CSV order not strict)
- Reporter crash: sets `_crash_event`, submit() checks and raises to main thread
- Checkpoint/resume: deferred to future (batch-level first)

**How to apply:** When modifying evaluator, reporter, or sim_model error handling, check these rules before changing severity logic or on_error defaults.
