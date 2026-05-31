# Invoicely — Development Plan

> A personal, terminal-based invoicing assistant that turns Toggl time entries into
> Bulgarian-compliant, dual-language (EN + BG) invoices, stored entirely in a
> Proton Drive synced folder.

This document is the authoritative roadmap. It is written for **incremental
development**: every phase is broken into small, independently shippable steps,
each with the files to touch, the components involved, the key technical
decisions, and the risks to watch.

---

## 0. Guiding Principles

These constraints shape every decision below:

1. **Pure terminal app.** No GUI, no web server, no inbound webhooks. All
   external state is reached by **polling**.
2. **Proton Drive folder is the single source of truth.** No database. State
   lives as human-readable **YAML** + generated **PDFs** on disk. The app must be
   safe to run against a folder that a sync client is also touching.
3. **Human-in-the-loop.** The LLM drafts; the user confirms. Nothing is signed,
   sent, or finalized without explicit approval in the chat.
4. **Deterministic core, conversational shell.** Tax math, numbering, totals,
   and PDF layout are plain Python (testable, no LLM). The LLM only orchestrates
   tools and drafts free text. **The LLM never computes money.**
5. **Idempotent & resumable.** Re-running any step must not duplicate invoices,
   re-charge, or corrupt state. Long-running flows (signing, payment polling)
   survive restarts by reading state back from disk.
6. **Human-in-the-loop *development*.** Every step is built test-first, with the
   user gating each transition (see below). This is not optional ceremony — it is
   what makes the codebase safe to refactor later.

### Development workflow (test-first, human-gated)

Every "Step" / "Task" in this plan is implemented as a strict, gated cycle. The
implementer (human or AI) does **not** advance to the next gate without explicit
approval from the user.

1. **Write the test suite first.** Before any implementation, write the tests for
   the step — covering the intended behavior, edge cases, and the invariants
   called out in the plan (e.g. totals reconcile, numbering is gap-free, date
   ordering holds). Tests are written against the *intended* interface and are
   expected to fail (red).
2. **User reviews and approves the tests.** The user reads the test suite and
   confirms it captures the right behavior. **Nothing is implemented until the
   user is happy with the tests.** Iterate on the tests only at this gate.
3. **Implement against the approved tests.** Write the minimum implementation that
   makes the approved suite pass (green). The approved tests are the spec — do not
   silently change them to fit the implementation; if a test turns out wrong,
   raise it with the user.
4. **Full manual testing step.** After the suite passes, the user manually
   exercises the step (run it end-to-end, try real inputs). This may surface gaps,
   which **feed back into the test suite** — update/extend tests (back through the
   approval gate as needed), then adjust the implementation.

Practical notes:
- Keep steps small enough that a test suite for one is reviewable in a sitting —
  this is why the plan is decomposed the way it is.
- The deterministic core (`domain/`, `storage/`) is the easiest to drive this way
  and the most important to lock down, since everything else trusts it.
- The accumulated, user-approved suite is the safety net for future refactoring:
  refactors must keep the approved tests green, and any behavior change starts
  again at gate 1.

### A note on the stack version

The brief lists **Python 3.12**, but the repo is configured for **3.13**
(`.python-version`, `requires-python = ">=3.13"`, installed 3.13.5). This plan
targets **3.13**. If 3.12 is a hard requirement (e.g. for a dependency that lags
on 3.13), downgrade `requires-python` and `.python-version` first — decide this
in Phase 0 before locking dependencies.

---

## 1. Project Setup

### 1.1 Tooling & dependencies (`uv`)

Pin dependencies in `pyproject.toml` via `uv add`. Grouped by concern:

```bash
# Core runtime / UX
uv add rich typer pydantic pydantic-settings pyyaml python-dotenv platformdirs

# LLM + agent + RAG
uv add langgraph langchain-openai langchain-core langchain-community
uv add chromadb openai tiktoken

# Integrations
uv add httpx          # Toggl, Skribble, Revolut HTTP clients
uv add deepl          # official DeepL SDK

# PDF + signing
uv add weasyprint pyhanko pyhanko-certvalidator jinja2

# Dev tooling
uv add --dev pytest pytest-cov pytest-httpx respx ruff mypy types-PyYAML
```

**Key decisions**
- **Typer** for the CLI entry layer (subcommands like `invoicely chat`,
  `invoicely doctor`, `invoicely reindex`), **Rich** for all rendering.
- **Pydantic v2** models are the canonical in-memory representation; YAML files
  are just their serialized form. This gives validation for free on load.
- **httpx** (sync) for all API clients — one consistent client style, easy to
  mock with `respx` in tests.
- **WeasyPrint** needs native libs (`pango`, `cairo`, `gdk-pixbuf`,
  `libffi`). Document the `brew install` line; surface a clear error if missing.

**Challenge — WeasyPrint native deps on macOS:** failures are cryptic. Mitigate
with a `invoicely doctor` command (see 1.5) that imports WeasyPrint and reports
missing system libraries with the exact `brew` fix.

### 1.2 Folder structure (the repo)

```
invoicely/
├── main.py                      # thin shim -> invoicely.cli:app
├── pyproject.toml
├── .env.example                 # documented, committed
├── .env                         # secrets, gitignored
├── DEVELOPMENT_PLAN.md
├── CLAUDE.md
├── src/invoicely/
│   ├── __init__.py
│   ├── cli.py                   # Typer app: chat, doctor, reindex, version
│   ├── config.py                # pydantic-settings: paths, keys, company info
│   ├── paths.py                 # resolves Proton Drive subfolders, ensures they exist
│   │
│   ├── models/                  # Pydantic domain models (the data contracts)
│   │   ├── invoice.py           # Invoice, LineItem, Party, VatTreatment, Money
│   │   ├── timesheet.py         # Timesheet, TimeEntry, ProjectGroup
│   │   ├── client.py            # Client / contract metadata
│   │   └── payment.py           # Payment, MatchResult (Feature 2)
│   │
│   ├── storage/                 # the Proton Drive layer (YAML <-> models)
│   │   ├── yaml_store.py        # atomic read/write, schema versioning
│   │   ├── numbering.py         # invoice number allocation (gap-free, locked)
│   │   └── locking.py           # cross-process file lock (sync-safe writes)
│   │
│   ├── integrations/
│   │   ├── toggl.py             # fetch + group time entries
│   │   ├── deepl_client.py      # EN -> BG translation w/ caching
│   │   ├── skribble.py          # Feature 1
│   │   └── revolut.py           # Feature 2
│   │
│   ├── domain/                  # deterministic business logic (NO LLM, NO IO)
│   │   ├── vat.py               # VAT treatments + per-line override resolution
│   │   ├── totals.py            # subtotal, VAT, skonto, grand total (Decimal)
│   │   ├── grouping.py          # Toggl entries -> invoice line drafts
│   │   └── profitability.py     # Feature 3
│   │
│   ├── pdf/
│   │   ├── render.py            # Jinja2 + WeasyPrint -> PDF bytes
│   │   ├── sign.py              # pyHanko .pfx signing
│   │   └── templates/
│   │       ├── invoice.html.j2  # dual-language layout
│   │       ├── timesheet.html.j2
│   │       └── styles.css
│   │
│   ├── rag/
│   │   ├── index.py             # chunk + embed contracts/old invoices -> Chroma
│   │   └── retriever.py         # query interface used by the agent
│   │
│   ├── agent/
│   │   ├── graph.py             # LangGraph ReAct agent assembly
│   │   ├── tools.py             # @tool wrappers over domain/integrations
│   │   ├── prompts.py           # system prompt, tax/legal guardrails
│   │   └── session.py           # conversation history persistence
│   │
│   └── tui/
│       ├── chat.py              # Rich-based REPL loop
│       └── render.py            # tables, invoice previews, diffs, confirmations
└── tests/
    ├── conftest.py
    ├── fixtures/                # sample Toggl payloads, YAML invoices, certs
    └── ...
```

**Decision — `src/` layout.** Prevents import-shadowing and forces the package
to be installed (editable via `uv`), which keeps test imports honest.

### 1.3 Proton Drive data folder

Configured via `INVOICELY_DATA_DIR` (default `~/ProtonDrive/Invoicely/`).
`paths.py` ensures this structure exists on startup:

```
~/ProtonDrive/Invoicely/
├── config/
│   ├── company.yaml             # my legal entity, VAT id, bank, signing cert ref
│   └── clients/<slug>.yaml      # per-client: address, default VAT treatment, lang
├── timesheets/<year>/<id>.yaml + .pdf
├── invoices/<year>/<number>.yaml + .pdf
├── contracts/                   # source PDFs/text for RAG
├── rag/                         # Chroma persistent store + index manifest
├── payments/                    # Feature 2 ledger
├── expenses/                    # Feature 3
└── history/<session-id>.jsonl   # conversation history
```

**Decision — config split.** Secrets (API keys) live in repo-local `.env`.
*Business data* (company legal info, clients) lives in the Drive folder so it
syncs across machines and is versioned alongside invoices.

**Challenge — Proton Drive sync races.** Two failure modes: (a) writing while
sync reads a half-written file; (b) the same file edited on two machines.
Mitigations: **atomic writes** (write to `*.tmp` in the same dir, `fsync`,
`os.replace`); a **lock file** for number allocation; and **never** delete/rename
files the sync client may be mid-upload. Treat the folder as append-mostly.

### 1.4 Configuration & secrets

`config.py` uses `pydantic-settings`:

```
# .env.example  (committed, no real values)
OPENAI_API_KEY=
DEEPL_API_KEY=
TOGGL_API_TOKEN=
TOGGL_WORKSPACE_ID=
SKRIBBLE_API_KEY=          # Feature 1
SKRIBBLE_API_SECRET=
REVOLUT_API_TOKEN=         # Feature 2

INVOICELY_DATA_DIR=~/ProtonDrive/Invoicely
OPENAI_MODEL=gpt-4o
PDF_SIGNING_PFX_PATH=      # path to .pfx (kept OUTSIDE the synced folder)
PDF_SIGNING_PFX_PASSWORD=
```

**Decision — signing key handling.** The `.pfx` and its password are the most
sensitive secrets. Keep the `.pfx` **outside** the synced Drive folder and load
the password from the keychain or `.env`, never from a synced file.

### 1.5 First runnable artifact

Before any feature: make `uv run python main.py` (and `invoicely doctor`) work.
`doctor` checks: env vars present, data dir reachable, WeasyPrint imports,
OpenAI/DeepL/Toggl reachable (cheap auth ping), signing cert loadable. This is
the smoke test the user runs after setup and the diagnostic for every later bug.

---

## 2. MVP (Phase 0) — Detailed Tasks

Goal: *"From a Toggl date range, draft → confirm → generate a signed,
dual-language invoice PDF saved to Proton Drive, via a terminal chat."*

Build bottom-up: deterministic core first, integrations next, agent last. Each
step below is independently testable.

### Step 0 — Domain models (`models/`)
- **Files:** `models/invoice.py`, `models/timesheet.py`, `models/client.py`.
- Define `Money` (wraps `Decimal`, fixed currency, no float ever), `Party`,
  `VatTreatment` (enum: `BG_STANDARD_20`, `EU_REVERSE_CHARGE`, `NON_EU_ZERO`),
  `LineItem` (qty, unit price, optional per-line VAT override, EN+BG text),
  `Invoice` (number, dates, parties, lines, default VAT, totals, status).
- **Decision:** money as `Decimal`, serialized as strings in YAML to avoid float
  drift. Totals are computed, never stored as the source of truth (store them for
  display, recompute on load and assert equality).
- **Risk:** rounding. Fix a rounding policy (round half-up, 2 dp, per-line then
  sum) and encode it once in `domain/totals.py`.

### Step 1 — YAML storage layer (`storage/`)
- **Files:** `storage/yaml_store.py`, `storage/locking.py`, `storage/numbering.py`.
- Atomic write helper; load-with-validation (YAML → Pydantic); a `schema_version`
  field on every document for forward migration.
- **Numbering:** Bulgarian invoices need **sequential, gap-free** numbers that are
  **exactly 10 digits long** (zero-padded, e.g. `0000000042`) — this is a legal
  definition, not a display choice. Allocate under a file lock, persist the counter
  in `config/`, and validate the 10-digit format on every write. Allocation must be
  the *last* step before write so failed drafts don't burn numbers.
- **Date-ordering invariant:** number order must follow document-date order —
  *number ascending ⇒ date non-decreasing*. A higher number may never carry an
  earlier date than a lower one. Enforce on every issue; a backdated invoice cannot
  reuse an existing number and must instead be handled via cancel-and-reissue
  (**Feature 4, §6**).
- **Challenge:** gap-free numbering + date ordering + crash safety + sync.
  Allocate-and-commit in one locked transaction; reconcile on startup by scanning
  existing invoice files and warning on any gap, duplicate, or date-order violation.

### Step 2 — VAT & totals engine (`domain/vat.py`, `domain/totals.py`)
- Resolve effective VAT per line: per-line override falls back to invoice
  default. Implement the three treatments and the legally-required note text each
  one stamps on the invoice (e.g. reverse-charge clause, Art. references).
- **Skonto** = a manual **negative line item** (early-payment discount). Decide
  its VAT treatment explicitly (typically reduces the taxable base — confirm with
  the user / RAG legal text) and document it.
- **Decision:** keep all legally-mandated wording in data (per-client YAML / RAG),
  not hardcoded in Python, so it can be corrected without code changes.
- **Heavy test target** — this is pure functions; cover it exhaustively (2.7).

### Step 3 — Toggl integration (`integrations/toggl.py`, `domain/grouping.py`)
- Fetch time entries for a date range + workspace via Toggl Reports/Track API
  (httpx, token auth). Normalize into `TimeEntry` models.
- **Grouping:** auto-group by project + description into candidate line items
  (sum durations → hours → qty). Pure function in `domain/grouping.py`.
- **Challenge:** Toggl pagination + rate limits; rounding hours (decide:
  round per-entry or per-group, to what precision — make it a config knob).
- **Test:** record a real Reports API response as a fixture; test grouping offline.

### Step 4 — DeepL translation (`integrations/deepl_client.py`)
- Translate line descriptions EN → BG. **Cache** translations (keyed by source
  text hash) in the Drive folder so repeated descriptions aren't re-billed/re-sent.
- **Decision:** translation is suggestion, not gospel — the chat lets the user
  edit the BG text before finalizing.
- **Challenge:** DeepL formality/glossary for domain terms. Support a per-client
  glossary file to keep terminology consistent across invoices.

### Step 5 — RAG over contracts + old invoices (`rag/`)
- **Files:** `rag/index.py`, `rag/retriever.py`, `invoicely reindex` command.
- Chunk + embed contract text and prior invoices into a **persistent Chroma**
  store under `rag/`. Use OpenAI embeddings. Index manifest tracks source file
  hashes so `reindex` only re-embeds changed files.
- **Purpose:** consistency (rates, legal clauses, client-specific wording) and
  retrieving the correct legal text per VAT treatment.
- **Challenge:** PDFs need text extraction; scanned contracts need OCR (defer OCR
  — document the limitation, ingest text-based PDFs/`.txt`/`.md` first).

### Step 6 — PDF generation (`pdf/render.py` + templates)
- Jinja2 HTML templates → WeasyPrint → PDF bytes. **Dual-language** layout:
  EN + BG side-by-side or stacked per field. Must include all Bulgarian-mandated
  invoice fields (numbers, VAT ids, dates, treatment notes, totals breakdown).
- **Decision:** template-driven so layout changes don't touch Python. Render
  *timesheet* and *invoice* from the same CSS for visual consistency.
- **Challenge:** Cyrillic font embedding — bundle a font with full BG glyph
  coverage (e.g. a Noto/DejaVu family) and reference it in `styles.css`; verify
  glyphs actually embed in the output PDF.

### Step 7 — Digital signing (`pdf/sign.py`)
- Sign the generated PDF with **pyHanko** using the `.pfx` cert. Visible or
  invisible signature (decide; invisible is simplest for MVP).
- **Decision:** sign as the final, separate step on the rendered bytes, so an
  unsigned draft can always be previewed first.
- **Challenge:** PDF/A vs signing constraints, timestamp authority (optional),
  cert chain validation. Keep signing config in `.env`; fail loudly if the cert
  can't be loaded (covered by `doctor`).

### Step 8 — Agent + tools (`agent/`)
- **Files:** `agent/tools.py`, `agent/graph.py`, `agent/prompts.py`,
  `agent/session.py`.
- LangGraph **ReAct** agent over GPT-4o. Wrap deterministic functions as tools:
  `fetch_toggl_entries`, `group_into_lines`, `translate_to_bg`,
  `rag_search`, `compute_totals`, `allocate_invoice_number`, `render_pdf`,
  `sign_pdf`, `save_invoice`, `save_timesheet`.
- **Guardrails (prompt):** the LLM must call `compute_totals` for all money —
  it is forbidden from doing arithmetic itself; it must present a draft and get
  explicit user confirmation before `save`/`sign`.
- **Decision:** tools return structured Pydantic/JSON, not prose, so the agent
  reasons over real data. Confirmation is a tool too (`request_confirmation`),
  keeping the human-in-the-loop gate explicit and testable.

### Step 9 — Terminal chat UI (`tui/chat.py`, `tui/render.py`)
- Rich REPL: stream agent responses, render draft invoices as tables, show a
  clear diff/preview before confirmation, pretty-print errors.
- **Decision:** previews render the *actual* computed invoice (same totals
  engine), not the LLM's description of it.

### Step 10 — Conversation history (`agent/session.py`)
- Persist turns to `history/<session-id>.jsonl` in the Drive folder. Allow
  resuming a session. Keep it append-only (sync-friendly).

### MVP exit criteria
A full happy-path run: pick date range → Toggl fetch → grouped + translated
draft → user edits/confirms → correct VAT + totals → dual-language signed PDF +
YAML written to Proton Drive → session saved. Covered by an end-to-end test with
all externals mocked.

---

## 3. Feature 1 — Skribble Signing Flow

Goal: client signs a **timesheet** before the invoice exists. Invoice is created
**only** from signed timesheet data.

### Tasks
1. **Timesheet model + PDF** (`models/timesheet.py` done in MVP; add
   `pdf/templates/timesheet.html.j2`): render a dual-language timesheet from
   grouped Toggl data.
2. **Skribble client** (`integrations/skribble.py`): authenticate, create a
   signature request, upload the timesheet PDF, fetch status, download the signed
   document. httpx; all polling, no webhooks.
3. **State machine** for the signing lifecycle persisted in the timesheet YAML:
   `draft → sent_for_signature → signed → invoice_created` (+ `declined`,
   `expired`). Status is read from disk, so a restart resumes correctly.
4. **Polling command/tool** (`poll_skribble_status`): the agent (or a
   `invoicely poll` command) checks pending requests and advances state.
5. **Gate:** `create_invoice_from_timesheet` tool refuses unless status ==
   `signed`, and pulls line data from the **signed** timesheet snapshot (not a
   fresh Toggl fetch — the signed numbers are authoritative).

**Key decisions**
- The signed timesheet is **immutable**; the invoice references its id + hash.
- Polling is explicit and idempotent; store `skribble_request_id` + last-polled
  timestamp in YAML.

**Challenges**
- Long round-trips (client may sign days later) → must survive restarts: state on
  disk, not in memory. ✔ handled by step 3.
- Skribble API auth/format quirks → isolate in the client, fixture its responses.
- Avoiding double-send → idempotency key derived from timesheet id.

---

## 4. Feature 2 — Revolut Payment Tracking

Goal: poll Revolut Business transactions and reconcile them against open invoices.

### Tasks
1. **Payment models** (`models/payment.py`): `Payment` (amount, currency, date,
   reference, counterparty), `MatchResult` (invoice ↔ payment, confidence,
   method).
2. **Revolut client** (`integrations/revolut.py`): OAuth/token auth, fetch
   transactions since a cursor date. httpx, polling. Persist a `last_synced`
   cursor in `payments/`.
3. **Matching engine** (`domain/matching.py`, pure): match by (a) invoice number
   in the payment reference, (b) amount, (c) date proximity. Produce a confidence
   score; auto-match high confidence, queue the rest.
4. **Manual matching fallback** (chat tool + Rich UI): present unmatched payments
   and open invoices, let the user link them.
5. **Status & reporting:** update invoice `status` (`open → paid`/`partial`),
   and views for open invoices, paid invoices, revenue per client.

**Key decisions**
- Matching is deterministic & testable; the agent only *presents* and *applies*
  results.
- Invoice → payment is the link of record; store match metadata on both sides for
  auditability.

**Challenges**
- Multi-currency (BGN/EUR) and FX — normalize for comparison, store original.
- Partial payments / overpayments / one transfer covering several invoices →
  model payments-to-invoices as many-to-many with allocated amounts.
- Revolut Business API access & token refresh → isolate, document onboarding.

---

## 5. Feature 3 — Expense & Profitability Tracking

Goal: record expenses against clients/contracts and compute profitability.

### Tasks
1. **Expense model + store** (`models/expense.py`, `expenses/<year>/*.yaml`):
   amount, date, category, client/contract link, optional receipt path,
   deductible/VAT flags.
2. **Entry via chat:** tool to record an expense; optional RAG/LLM categorization
   suggestion (user confirms).
3. **Profitability engine** (`domain/profitability.py`, pure): revenue (from paid
   invoices, Feature 2) − expenses, grouped per client/contract and per period.
4. **Reports** (Rich tables): per-client P&L, period summaries, top clients.

**Key decisions**
- Reuses Feature 2's revenue data — build after Feature 2 so revenue is real.
- Keep it reporting-only (no accounting-grade ledger) for a personal tool;
  document that boundary.

**Challenges**
- Consistent currency across revenue & expenses → reuse the FX normalization from
  Feature 2.
- Allocating shared expenses across clients → support an explicit split or leave
  unallocated; don't guess.

---

## 6. Feature 4 — Invoice Cancellation & Reissue

Goal: cancel an issued invoice (documented, never deleted) and reissue it with a
**new** number, to keep the legally-required ordering intact.

### The constraint
Bulgarian numbering is not only sequential and gap-free (§2 Step 1) — the
**number order must follow the document-date order**: a higher invoice number may
never carry an earlier invoice date than a lower one. So a number can never be
reused for a different (later) date.

Worked example: `0000000001` is issued dated **Mar 31** and `0000000002` dated
**Apr 3**. The client later needs the *content* of invoice #1 dated **Apr 5**.
Editing #1's date would put a low number after a high one — illegal. Instead:
**cancel `0000000001`** (documented), and **reissue the content as the next
number `0000000003` dated Apr 5**, which preserves order.

### Tasks
1. **Status & lifecycle on the invoice model** (`models/invoice.py`): add
   `status` (`issued → cancelled`, plus `reissued` linkage) and cross-reference
   fields: `cancelled_by` / `cancels` and `reissued_as` / `reissue_of`. A cancelled
   invoice keeps its number and PDF forever — it is **never deleted or renumbered**.
2. **Cancellation record** (`models/cancellation.py` or fields on the invoice):
   reason (free text, e.g. "date-ordering correction"), timestamp, operator, and
   a reference to the replacement invoice. Persist as YAML alongside the invoice.
3. **Date-ordering invariant** (`domain/numbering` / `storage/numbering.py`): a
   pure check `assert_date_order(invoices)` enforcing *number ascending ⇒ date
   non-decreasing*. Run it on every issue and on startup reconciliation (alongside
   the gap/duplicate scan). Reject any issue that would violate it, and explain
   why (pointing the user toward cancel-and-reissue).
4. **Cancellation document/PDF** (`pdf/templates/cancellation.html.j2`): generate
   a dual-language **credit note / cancellation document** referencing the
   original number, and sign it like any other PDF (`pdf/sign.py`). The original
   PDF stays untouched.
5. **Reissue flow** (tool `cancel_and_reissue_invoice` + chat UI): copy the source
   invoice's line data into a fresh draft, allocate the **next** number, set the
   new date, link both directions (`reissue_of` / `reissued_as`), then run the
   normal confirm → render → sign → save path. The original transitions to
   `cancelled` atomically with the new issue.
6. **Reporting impact:** cancelled invoices are excluded from revenue/open totals
   (Feature 2) and profitability (Feature 3); the cancellation/reissue chain stays
   visible for audit.

**Key decisions**
- **Append-only, never mutate.** Cancellation is a new documented state + a new
  document, not an edit or delete — matches the audit/sync constraints (§0).
- The replacement is a normal next-in-sequence invoice; there is no "reused"
  number. The link fields are what tie the story together for auditors.
- The date-ordering invariant lives in `domain/` (pure, tested) and is enforced at
  every issue, not just relied upon by convention.

**Challenges**
- **Partial sequences / many invoices same day** — date order is *non-decreasing*,
  so equal dates are fine; only a strictly-earlier date under a higher number is
  illegal. Encode exactly that.
- **Already-paid invoice being cancelled** (Feature 2) — must unwind/reattach the
  payment match to the reissued invoice; surface this explicitly rather than
  silently re-matching.
- **Skribble-signed timesheets** (Feature 1) — a reissue should reference the same
  signed timesheet; don't force re-signing for a pure numbering/date correction.

---

## 7. Recommended Implementation Order

1. **Phase 0 setup** (§1): `uv` deps, `config.py`, `paths.py`, `doctor`,
   `.env.example`. *Stop when `invoicely doctor` is green.*
2. **Deterministic core** (MVP steps 0–2): models, YAML store, numbering +
   date-ordering invariant, VAT + totals. Fully unit-tested before any IO. *This
   is the foundation everything trusts — get it right first.*
3. **Toggl + grouping** (step 3), then **DeepL** (step 4).
4. **PDF render** (step 6) → **signing** (step 7). Get a correct, signed,
   dual-language PDF from hand-written YAML *before* involving the LLM.
5. **RAG** (step 5).
6. **Agent + tools** (step 8) → **chat UI** (step 9) → **history** (step 10).
   *MVP complete.*
7. **Feature 1 (Skribble)** — reorders the flow to timesheet-first; do it once
   timesheet PDF + agent exist.
8. **Feature 2 (Revolut)** — independent; enables real revenue data.
9. **Feature 3 (Expenses/Profitability)** — depends on Feature 2's revenue.
10. **Feature 4 (Cancellation & reissue)** — can land right after the MVP (it only
    needs the numbering core + PDF/signing), but place it after the features that
    touch its edge cases (paid invoices, signed timesheets) so unwinding logic is
    written once with those in mind.

Rationale: each layer is usable and testable before the next depends on it. The
LLM is added **last** in the MVP so the deterministic pieces are already trusted —
the agent only orchestrates known-good tools.

---

## 8. Testing Strategy

**Philosophy:** the money/tax/numbering core is pure and exhaustively
unit-tested; integrations are tested against **recorded fixtures** (never live
APIs in CI); the agent is tested for *tool orchestration*, not LLM prose.

**Tests come first and are user-approved.** Per the test-first, human-gated
workflow in §0, each step's suite is written and approved *before* its
implementation, and is extended after the manual-testing gate. The layers below
describe *what* each kind of test covers; §0 describes *when* it is written and
*who* signs it off. The approved suite is the refactoring safety net.

### Layers
- **Unit (the core, highest coverage):**
  - `domain/totals.py` & `domain/vat.py`: every VAT treatment, per-line overrides,
    skonto, rounding edge cases, mixed-treatment invoices. Property-style checks
    (totals always reconcile).
  - `storage/numbering.py`: sequential allocation, gap/duplicate detection,
    concurrent-allocation under lock.
  - `domain/grouping.py`, `domain/matching.py`, `domain/profitability.py`: pure,
    fixture-driven.
- **Integration (mocked transport):** `respx`/`pytest-httpx` against recorded
  Toggl / DeepL / Skribble / Revolut payloads stored in `tests/fixtures/`. Test
  pagination, auth failure, rate-limit handling, malformed responses.
- **PDF & signing:** render to bytes; assert structure (required fields present,
  Cyrillic glyphs embedded) by parsing the PDF; verify the pyHanko signature
  validates against a **test cert** committed to fixtures (never the real `.pfx`).
- **Storage/sync safety:** simulate interrupted writes (kill between tmp-write and
  replace) and assert no corrupt/partial YAML is ever loaded; test atomic-write
  and lock behavior.
- **Agent:** stub the LLM / use a scripted tool sequence; assert the agent calls
  `compute_totals` for money, never finalizes without `request_confirmation`, and
  gates invoice creation on signed status (Feature 1). Keep one **live smoke
  test** behind a marker (`-m live`) for manual runs, excluded from CI.
- **End-to-end (mocked externals):** the full MVP happy path (§2 exit criteria) as
  a single test producing a real signed PDF + YAML in a temp data dir.

### Mechanics
- `pytest` + `pytest-cov`; `ruff` (lint+format) and `mypy` in CI.
- `tests/fixtures/` holds: sample Toggl responses, sample YAML invoices/clients, a
  throwaway test signing cert, and golden expected-totals tables.
- A temp-dir `INVOICELY_DATA_DIR` fixture so tests never touch the real Proton
  Drive folder.
- Target: ~100% on `domain/` and `storage/`; pragmatic coverage elsewhere.

---

## 9. Cross-Cutting Risks (summary)

| Risk | Where | Mitigation |
|------|-------|-----------|
| Float rounding in money | totals/VAT | `Decimal` everywhere, YAML strings, fixed rounding policy, exhaustive tests |
| Proton Drive sync races | storage | atomic write + `os.replace`, file locks, append-mostly, no rename mid-sync |
| Gap-free invoice numbering | numbering | locked allocate-and-commit, startup reconciliation scan |
| Number/date ordering (backdating) | numbering, Feature 4 | date-order invariant enforced on every issue; backdating handled by cancel-and-reissue, never number reuse |
| LLM doing math / hallucinating totals | agent | money only via `compute_totals` tool; previews from real engine |
| Cyrillic rendering in PDF | pdf | bundle full-glyph font, assert embedded glyphs in tests |
| Signing key exposure | config/sign | `.pfx` outside synced folder, password from env/keychain |
| Long async signing waits | Feature 1 | state on disk, polling, resumable |
| Multi-currency / partial payments | Features 2–3 | normalize FX for compare, store original, many-to-many allocation |
| WeasyPrint native deps | setup | `doctor` command with actionable error |

---

## 10. Open Questions (resolve as you go)

- **Python 3.12 vs 3.13** — repo is 3.13; brief said 3.12. Confirm in Phase 0.
- Exact Bulgarian invoice **mandatory fields** and **legal note wording** per VAT
  treatment — seed from real contracts via RAG; verify with an accountant.
- Skonto's precise **VAT base impact** — confirm legally before shipping.
- Visible vs invisible PDF signature, and whether a **timestamp authority** is
  required for the audit use-case.
- Invoice **number format**: confirmed **exactly 10 digits, zero-padded**. Still
  open: is the sequence continuous across years, or reset/scoped per year?
