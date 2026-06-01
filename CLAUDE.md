# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Invoicely** — a personal, terminal-based invoicing assistant. It turns Toggl
time entries into Bulgarian-compliant, dual-language (EN + BG) invoices, stored
entirely in a Proton Drive synced folder. Python 3.13, managed with `uv`.

See **[DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md)** for the full phased roadmap
(setup → MVP → Skribble signing → Revolut payments → profitability), per-step
tasks, technical decisions, risks, and the testing strategy. Consult it before
starting any new piece of work.

## Commands

```bash
uv run python main.py       # run the app (thin shim -> invoicely.cli)
invoicely doctor            # environment/health smoke test (build this first)
invoicely chat              # terminal chat interface
invoicely reindex           # rebuild the RAG index over contracts/invoices
uv run pytest               # run tests
uv run ruff check .         # lint
uv run mypy src             # type-check
uv add <package>            # add a dependency
```

## Development workflow (MANDATORY — test-first, human-gated)

Every step/task is built as a strict gated cycle. **Do not advance to the next
gate without the user's explicit approval.**

1. **Write the test suite first** — before any implementation. Cover intended
   behavior, edge cases, and the invariants (totals reconcile, numbering gap-free
   + 10 digits, date ordering holds). Tests are red at this point.
2. **User approves the tests** — present the suite and wait. **Implement nothing
   until the user is happy with the tests.** Iterate on tests only at this gate.
3. **Implement against the approved tests** — minimum code to go green. The
   approved tests are the spec; do not quietly change them to fit the code. If a
   test seems wrong, raise it with the user.
4. **Full manual testing** — the user exercises the step end-to-end. Findings
   feed back into the suite (re-approve changes), then adjust the implementation.

The accumulated, user-approved suite is the safety net for refactoring: refactors
keep approved tests green; any behavior change restarts at gate 1. Keep steps
small enough that one step's suite is reviewable in a sitting.

### MANUAL vs Claude-led steps

Steps in DEVELOPMENT_PLAN.md are tagged **🔨 MANUAL (human-led)** or _Claude-led_.

- **MANUAL steps are written by the user by hand — Claude Code never completes
  them end-to-end.** They are kept manual on purpose, to keep the user's craft
  sharp. On a MANUAL step Claude's role is strictly **supportive**: explain
  approaches, sketch options, review the user's code, write/critique tests at the
  test gate, look up APIs, debug a specific failure the user is stuck on. Do
  **not** write the bulk of the production code, do **not** "just finish it", and
  do **not** hand over a complete solution that pre-empts the learning. Default to
  the smallest useful nudge and let the user drive. If a request would have you
  implement a MANUAL step wholesale, pause and confirm scope first.
- **Claude-led steps** may be implemented by Claude directly — still inside the
  gated cycle above (tests approved first, manual-testing gate after).

The marker governs only *who writes the implementation*; the test-first, gated
cycle applies to every step regardless.

## Core principles (these override convenience)

1. **Pure terminal app.** No GUI, no web server, no inbound webhooks — reach
   external state by **polling** only.
2. **Proton Drive folder is the single source of truth.** No database. State is
   human-readable **YAML** + generated **PDFs** on disk. Writes must be safe
   while a sync client touches the same folder.
3. **Human-in-the-loop.** The LLM drafts; the user explicitly confirms before
   anything is saved, signed, or sent.
4. **Deterministic core, conversational shell.** Tax math, totals, numbering,
   and PDF layout are plain, tested Python. **The LLM never computes money** — it
   only orchestrates tools and drafts free text.
5. **Idempotent & resumable.** Re-running a step must never duplicate invoices,
   re-charge, or corrupt state. Long flows survive restarts by reading state
   back from disk.

## Money & tax (get this right)

- All monetary values use `Decimal`, serialized as **strings** in YAML — never
  float. One fixed rounding policy lives in `domain/totals.py`.
- VAT treatments: `BG_STANDARD_20`, `EU_REVERSE_CHARGE`, `NON_EU_ZERO`. Set a
  per-invoice default with per-line override. Legally-required note text is data
  (per-client YAML / RAG), not hardcoded.
- **Skonto** (early-payment discount) is a manual **negative line item**.
- Bulgarian invoice numbers must be **sequential, gap-free, and exactly 10 digits
  long** (zero-padded) — allocated under a file lock as the last step before write
  (`storage/numbering.py`).
- **Number order must follow document-date order** (number ascending ⇒ date
  non-decreasing). A backdated invoice can never reuse an existing number: cancel
  the original (documented, never deleted) and **reissue** with the next number —
  see Feature 4 in the plan. Cancellation is append-only state + a new signed
  document, never an edit or delete.

## Architecture

Tech stack: Rich (TUI) · Typer (CLI) · Pydantic v2 (domain models) · LangGraph
ReAct agent over OpenAI GPT-4o · DeepL (EN→BG) · Chroma (RAG) · WeasyPrint (run
in a **podman** container, not on the host — macOS native deps are too brittle) +
pyHanko (PDF render + `.pfx` signing) · httpx (Toggl/Skribble/Revolut clients) ·
YAML on disk.

Source lives under `src/invoicely/`. Layered, with strict dependency direction
(agent → domain/integrations → models; `domain/` is pure, no IO, no LLM):

- `models/` — Pydantic domain models (the data contracts).
- `storage/` — YAML read/write (atomic), file locking, invoice numbering.
- `domain/` — **pure** business logic: VAT, totals, grouping, matching,
  profitability. No IO, no LLM. Highest test coverage.
- `integrations/` — Toggl, DeepL, Skribble, Revolut clients (httpx, polling).
- `pdf/` — Jinja2 templates + WeasyPrint render (HTML→PDF in a podman container,
  bytes returned to host) + pyHanko signing (on host).
- `rag/` — Chroma index/retriever over contracts + old invoices.
- `agent/` — LangGraph ReAct agent, tools, prompts, session history.
- `tui/` — Rich chat REPL and rendering.

Data folder (`INVOICELY_DATA_DIR`, default `~/ProtonDrive/Invoicely/`):
`config/` (company + clients), `timesheets/`, `invoices/`, `contracts/`, `rag/`,
`payments/`, `expenses/`, `history/`.

## Conventions

- Build **bottom-up**: deterministic core (models, storage, totals/VAT) is
  written and fully unit-tested before integrations; the agent comes **last**.
- Tools return structured Pydantic/JSON (not prose) so the agent reasons over
  real data. Previews render the *actual* computed invoice, not the LLM's
  description of it.
- Secrets (API keys) in repo-local `.env` (gitignored; see `.env.example`).
  Business data (company, clients) lives in the synced Drive folder. The signing
  `.pfx` is kept **outside** the synced folder.
- Integrations are tested against recorded fixtures in `tests/fixtures/` — never
  live APIs in CI. Tests use a temp `INVOICELY_DATA_DIR`, never the real folder.

## Status

Early-stage. Currently a single `main.py` entry point. Implement per the
phased order in [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md#6-recommended-implementation-order),
starting with Phase 0 setup and a green `invoicely doctor`.
