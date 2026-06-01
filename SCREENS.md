# Invoicely — TUI Screens (Textual)

> Exploratory sketch of the terminal UI. This is a **design draft** for drawing
> screens with [Textual](https://textual.textualize.io/), not a spec. It maps
> what information lives on each screen and how the screens relate. It does not
> change the core principles in [CLAUDE.md](CLAUDE.md) or the roadmap in
> [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) — the deterministic core and the
> chat agent remain the heart of the app; this is the *visual* shell around them.

## Design constraints (carried over from the plan)

- **Read-from-disk, human-in-the-loop.** Screens render state read from the
  Proton Drive YAML/PDF folder. Nothing is signed/sent/saved without an explicit
  confirm step. The TUI never computes money — it displays what `domain/totals.py`
  computed.
- **Polling, never webhooks.** "Live" data (Skribble status, Revolut payments) is
  the result of the last poll; show the *last-polled* timestamp, never imply push.
- **The chat agent is always reachable.** Screens are for *seeing* and
  *navigating* state; the agent (`tui/chat.py`) is for *doing*. A global key
  (e.g. `c`) drops into chat from anywhere, optionally pre-scoped to the current
  selection (e.g. "this client", "this invoice").
- **Dual-language.** Where a field has EN + BG, the screen shows EN by default and
  can toggle to BG (`g`), since the generated documents are bilingual.

## Global layout & navigation

```
┌─ Invoicely ───────────────────────────────────── 2026-06-01 · BGN/EUR ─┐
│  Dashboard   Clients   Flow   Invoices   Expenses              [chat: c]│  ← top tabs
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│                          (active screen body)                            │
│                                                                           │
├─────────────────────────────────────────────────────────────────────────┤
│ d Dashboard  l Clients  f Flow  i Invoices  e Expenses · c Chat · q Quit │  ← Footer
└─────────────────────────────────────────────────────────────────────────┘
```

- Five primary screens as tabs: **Dashboard · Clients · Flow · Invoices · Expenses**.
- Header shows the app, today's date, and active currency context.
- Footer shows key bindings (Textual `Footer` + `BINDINGS`).
- Common keys everywhere: `g` toggle EN/BG, `c` chat, `r` refresh/poll,
  `/` filter, `?` help, `q` quit.

> On naming: the request floated **"Finances or better Flow"**. This draft uses
> **Flow** for the work-pipeline screen (Toggl → timesheet → invoice → payment),
> because the *financial summary* numbers naturally live on the **Dashboard**.
> If a dedicated finances/P&L screen is wanted later, it can split off from the
> Dashboard's "Money" panels. Open question — see the end.

---

## 1. Dashboard

**Purpose:** the at-a-glance "where do things stand" screen. First thing seen on
launch. Read-only summary; every tile is a jump-off point into a detail screen.

```
┌─ Dashboard ───────────────────────────────────────────────────────────┐
│ ┌─ This month (Jun 2026) ─────────┐ ┌─ Outstanding ──────────────────┐ │
│ │ Invoiced      4 200.00 BGN      │ │ Open invoices        3         │ │
│ │ Paid          1 800.00 BGN      │ │ Overdue              1  ⚠       │ │
│ │ Expenses        320.00 BGN      │ │ Awaiting signature   2         │ │
│ │ Net           3 880.00 BGN      │ │ Unmatched payments   1         │ │
│ └─────────────────────────────────┘ └────────────────────────────────┘ │
│ ┌─ Needs attention ───────────────────────────────────────────────────┐ │
│ │ ⚠  Invoice 0000000041  overdue 6 days        Acme Ltd   1 200 BGN   │ │
│ │ ✎  Timesheet TS-2026-014 signed → ready to invoice   Beta GmbH      │ │
│ │ ?  Payment 412.00 EUR (2026-05-29) unmatched                        │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│ ┌─ Recent activity ───────────────────────────────────────────────────┐ │
│ │ 2026-05-30  Invoice 0000000042 issued + signed     Acme Ltd         │ │
│ │ 2026-05-29  Timesheet TS-2026-014 sent for signing Beta GmbH        │ │
│ │ 2026-05-28  Payment matched → 0000000038            Gamma OOD        │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│ Last polled: Toggl 12m ago · Skribble 12m ago · Revolut 12m ago  [r]   │
└─────────────────────────────────────────────────────────────────────────┘
```

**Information on this screen**
- **Period money summary** (selected period, default current month): invoiced,
  paid, expenses, net. Currency-aware (BGN/EUR, FX-normalized for the rollup;
  original kept). All figures sourced from the deterministic engine, never
  recomputed in the UI.
- **Outstanding counters:** open / overdue / awaiting-signature / unmatched —
  each links to a filtered view on the relevant screen.
- **Needs-attention queue:** the actionable items, prioritized (overdue,
  signed-and-ready-to-invoice, unmatched payments, date-order/numbering warnings
  from the startup reconciliation scan).
- **Recent activity:** append-only log of issues/sign/match events (from
  `history/` + invoice/payment state).
- **Poll freshness:** last-polled timestamps per integration; `r` triggers a poll.

**Navigation:** Enter on any tile/row → the corresponding detail screen,
pre-filtered. `c` → chat scoped to the highlighted item.

---

## 2. Clients

**Purpose:** the directory of clients (`config/clients/<slug>.yaml`) and the
per-client picture: contact/legal data, defaults that drive invoicing, and the
history of work and money with that client.

```
┌─ Clients ─────────────────────────────────────────────────────────────┐
│ ┌─ Clients ─────────────┐ ┌─ Acme Ltd ──────────────────────────────┐ │
│ │ > Acme Ltd      BG ⚠1 │ │ Legal name  Acme Ltd                    │ │
│ │   Beta GmbH     EU    │ │ VAT id      BG123456789                 │ │
│ │   Gamma OOD     BG    │ │ Address     1 Vitosha Blvd, Sofia       │ │
│ │   Delta Inc     non-EU│ │ Country     BG    Language  EN          │ │
│ │                       │ │ VAT default BG_STANDARD_20              │ │
│ │ [/ filter]            │ │ Rate        80.00 BGN / h               │ │
│ │ [n new]               │ │ Glossary    acme-glossary.yaml          │ │
│ │                       │ │ Contract(s) 2 in RAG  ⟶ [v view]        │ │
│ └───────────────────────┘ ├─────────────────────────────────────────┤ │
│                           │ Invoices  12 · Open 1 (⚠ overdue)       │ │
│                           │ Revenue   38 400 BGN (paid, ytd)        │ │
│                           │ Last invoice 0000000041 · 2026-05-20    │ │
│                           │ ┌─ Recent invoices ────────────────────┐│ │
│                           │ │ 0000000041  2026-05-20  open ⚠       ││ │
│                           │ │ 0000000037  2026-04-20  paid         ││ │
│                           │ └──────────────────────────────────────┘│ │
│                           │ [c chat about this client]              │ │
│                           └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

**Information on this screen**
- **List (left):** all clients with country/VAT-region badge and an alert count.
- **Detail (right) — identity & legal:** legal name, VAT id, billing address,
  country, **default VAT treatment**, default invoice language, default
  hourly/day rate (or rate card), currency.
- **Invoicing knobs:** glossary file (DeepL terminology), any client-specific
  legal note overrides, payment terms (net days → drives "overdue").
- **Contracts/RAG:** which contract documents are indexed for this client.
- **Rollups:** invoice count, open/overdue, paid revenue (ytd + lifetime), last
  invoice number/date, average days-to-pay.
- **Recent invoices** list (jumps to Invoices screen filtered to this client).

**Actions:** `n` new client (form → writes YAML on confirm), `e` edit (confirm
before write), `v` view contract, `c` chat scoped to client. Edits are
confirm-gated and atomic per the storage rules.

---

## 3. Flow  (the work pipeline)

**Purpose:** the heart of "getting from time to money". A pipeline view of every
engagement as it moves **Toggl → grouped draft → timesheet (sign) → invoice →
payment**. This is where the *process state* lives (the lifecycle the plan
describes for Skribble signing and Revolut matching).

```
┌─ Flow ────────────────────────────────────────────────────────────────┐
│  Toggl pull   →  Timesheet   →  Signing    →  Invoice    →  Payment    │
│ ┌───────────┐  ┌───────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│ │ Beta GmbH │  │ TS-026-014│  │ TS-026-013│  │ 000…0041 │  │ 000…037 │ │
│ │ May 1–31  │  │ draft     │  │ sent  3d  │  │ issued   │  │ paid ✓  │ │
│ │ 42.5 h    │  │ 42.5 h    │  │ Acme Ltd  │  │ open ⚠   │  │ Gamma   │ │
│ │ [group →] │  │ [sign →]  │  │ [poll r]  │  │ [pay?]   │  │         │ │
│ └───────────┘  └───────────┘  └──────────┘  └──────────┘  └─────────┘ │
│ ┌─ Selected: TS-2026-014 (Beta GmbH, May 2026) ───────────────────────┐│
│ │ Grouped lines (from Toggl, hours → qty):                            ││
│ │   API integration work      28.0 h   @ 90.00 EUR   2 520.00 EUR     ││
│ │   Code review                14.5 h   @ 90.00 EUR   1 305.00 EUR     ││
│ │ EU_REVERSE_CHARGE · note: "Reverse charge, Art. 21(2)…"             ││
│ │ Status: draft   ·   Toggl pulled 12m ago                            ││
│ │ [t translate BG]  [s send for signature]  [c chat]                  ││
│ └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

**Information on this screen**
- **Pipeline columns** = lifecycle stages, each card = one engagement/timesheet/
  invoice at that stage:
  - **Toggl pull:** client + date range + total hours fetched (not yet grouped).
  - **Timesheet (draft):** grouped candidate lines, hours, the resolved VAT
    treatment + legal note, EN/BG state.
  - **Signing:** Skribble state (`sent_for_signature / signed / declined /
    expired`), days waiting, `skribble_request_id`, last-polled.
  - **Invoice:** allocated number, issue date, `issued / open / overdue /
    cancelled`, totals.
  - **Payment:** matched payment(s), `paid / partial`, match confidence.
- **Selected-item detail (bottom):** the grouped lines with qty/rate/amount, the
  VAT treatment and stamped legal note, status + last-poll time, and the
  stage-appropriate actions (group, translate, send, poll, create-invoice, match).
- **Gates are visible:** e.g. "create invoice" is disabled until the timesheet is
  `signed` (Feature 1 rule), with a tooltip saying why.

**Why a pipeline here:** it makes the *resumable, idempotent* state from the plan
legible — each card is backed by YAML on disk, so a restart redraws the same
board. Actions hand off to the agent/tools; the board only reflects state.

---

## 4. Invoices

**Purpose:** the ledger — every issued document, the legally-significant view.
Numbering, dates, status, totals, and the cancel/reissue chain (Feature 4).

```
┌─ Invoices ────────────────────── 2026 ▾ · all clients ▾ · status: all ▾ ┐
│ Number       Date        Client      Status     VAT          Total      │
│ 0000000042   2026-05-30  Acme Ltd    paid       BG 20%     1 440.00 BGN │
│ 0000000041   2026-05-20  Acme Ltd    overdue ⚠  BG 20%     1 200.00 BGN │
│ 0000000040   2026-05-12  Beta GmbH   open       reverse    3 825.00 EUR │
│ 0000000039   2026-05-03  Delta Inc   cancelled  zero       2 000.00 USD │
│   ↳ reissued as 0000000043                                              │
│ ─────────────────────────────────────────────────────────────────────  │
│ ┌─ 0000000041 ────────────────────────────────────────────────────────┐│
│ │ Acme Ltd · issued 2026-05-20 · due 2026-06-04 (overdue 6d ⚠)        ││
│ │ Lines:                                                               ││
│ │   Consulting   12.0 h @ 80.00   960.00                              ││
│ │   Travel        1     150.00    150.00                              ││
│ │ Subtotal 1 110.00 · VAT 20% 222.00 · Skonto −132.00 · Total 1 200.00││
│ │ VAT: BG_STANDARD_20 · Lang EN+BG · Signed ✓ (pyHanko)               ││
│ │ Files: 0000000041.yaml · 0000000041.pdf                             ││
│ │ [o open PDF] [p record payment] [x cancel & reissue] [c chat]       ││
│ └──────────────────────────────────────────────────────────────────────┘│
│ ✓ numbering: gap-free, 10-digit, date-order OK   (reconciled on start)  │
└─────────────────────────────────────────────────────────────────────────┘
```

**Information on this screen**
- **Table:** number (10-digit, zero-padded), document date, client, **status**
  (`issued / open / overdue / paid / partial / cancelled / reissued`), VAT
  treatment, total (original currency). Sortable by number or date.
- **Cancel/reissue chains** shown inline (`↳ reissued as …` / `↳ cancels …`) so
  the Feature-4 story is auditable at a glance.
- **Detail (selected):** parties, dates (issue + due), full line items
  (qty/unit/amount), the **totals breakdown** (subtotal, VAT per treatment,
  skonto negative line, grand total) exactly as computed by `domain/totals.py`,
  language, signature status, and the on-disk file paths (YAML + PDF).
- **Numbering health bar:** result of the startup reconciliation scan — gap-free,
  10-digit, date-order invariant holds (or a warning pointing to the offender).

**Actions:** `o` open the signed PDF, `p` record/match a payment, `x` cancel &
reissue (the Feature-4 flow — copies lines into a new draft, allocates the next
number, links both directions, confirm → render → sign → save), `c` chat. All
mutations are confirm-gated and append-only; a cancelled invoice/PDF is never
deleted or renumbered.

**Filters:** year (continuous-vs-per-year is an open question in the plan),
client, status.

---

## 5. Expenses

**Purpose:** record costs against clients/contracts and feed profitability
(Feature 3). Reporting-only, not an accounting ledger.

```
┌─ Expenses ─────────────────────── 2026 ▾ · client: all ▾ · category ▾ ──┐
│ Date        Category      Description        Client     Amount   VAT    │
│ 2026-05-28  Software      JetBrains licence  —          240.00   20% ✓  │
│ 2026-05-21  Travel        Train Sofia–Plovdiv Acme Ltd   38.00   20% ✓  │
│ 2026-05-10  Hardware      Monitor            —          560.00   20% ✓  │
│ ─────────────────────────────────────────────────────────────────────  │
│ ┌─ Selected: Train Sofia–Plovdiv ─────────────────────────────────────┐│
│ │ Date 2026-05-21 · Category Travel · Client Acme Ltd                 ││
│ │ Amount 38.00 BGN · VAT 20% deductible ✓                             ││
│ │ Receipt receipts/2026/train-0521.pdf  [o open]                      ││
│ │ Notes  client visit                                                 ││
│ │ [e edit] [c chat]                                                   ││
│ └──────────────────────────────────────────────────────────────────────┘│
│ ┌─ Profitability (Jun 2026, per client) ──────────────────────────────┐│
│ │ Client      Revenue(paid)   Expenses    Net        Margin           ││
│ │ Acme Ltd      18 400 BGN       38 BGN   18 362 BGN   99%            ││
│ │ Beta GmbH      7 650 EUR        0        7 650 EUR  100%            ││
│ │ Unallocated         —         800 BGN     −800 BGN    —             ││
│ └──────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

**Information on this screen**
- **Expense list** (`expenses/<year>/*.yaml`): date, category, description,
  client/contract link (or unallocated), amount + currency, VAT %/deductible
  flag, receipt path.
- **Detail (selected):** full record incl. receipt link and notes.
- **Profitability panel** (Feature 3, pure `domain/profitability.py`): revenue
  (from **paid** invoices via Feature 2) − expenses, grouped per client and
  period, with margin. Shared/unallocated expenses shown explicitly (the plan
  says "don't guess" the split).

**Actions:** `n` new expense (with optional LLM/RAG category suggestion the user
confirms), `e` edit, `o` open receipt, `c` chat. Currency normalized for the
rollup, original stored.

---

## Cross-screen patterns

- **Confirm-before-write modal:** any action that writes YAML / renders / signs /
  sends pops a confirmation showing the *actual computed* result (totals from the
  real engine, not a description). Mirrors the chat agent's `request_confirmation`.
- **Poll banner:** integration-backed screens show last-polled time + a manual
  `r` poll; never imply live push.
- **EN/BG toggle (`g`):** flips bilingual fields between English and Bulgarian.
- **Chat hand-off (`c`):** opens the chat REPL pre-scoped to the current
  selection so the agent has context ("draft invoice for this signed timesheet").
- **Alerts/warnings (`⚠`):** overdue, numbering/date-order violations, signing
  expired, unmatched payments — surfaced on Dashboard and inline where relevant.

## Open questions

1. **"Flow" vs a dedicated "Finances" screen.** This draft folds financial
   summaries into the **Dashboard** and uses **Flow** for the work pipeline. If a
   richer P&L / revenue / cash-flow view is wanted, split it into its own sixth
   screen or a sub-tab of Expenses. *Decide based on how much money-reporting depth
   is needed.*
2. **Where does "create invoice" live** — only on **Flow** (pipeline-driven), or
   also a "+new" on **Invoices**? Pipeline-first matches Feature 1 (timesheet →
   sign → invoice), but ad-hoc invoices may need a direct path.
3. **Year scoping** of the Invoices/Expenses tables ties to the still-open plan
   question: is invoice numbering continuous across years or reset per year?
4. **How much the TUI does vs the chat agent.** This draft keeps screens
   read/navigate-first and routes *doing* through the agent + confirm modals.
   Confirm that division before building widgets.
