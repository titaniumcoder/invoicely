# Invoicely

A personal, terminal-based invoicing assistant. Invoicely turns
[Toggl](https://toggl.com/) time entries into Bulgarian-compliant, dual-language
(English + Bulgarian) invoices — drafted in a chat, confirmed by you, then
rendered to a signed PDF and stored entirely in a [Proton Drive](https://proton.me/drive)
synced folder.

It's a single-person tool, built for my own freelancing workflow, but it doubles
as a worked example of two things that are surprisingly fiddly to get right:

- **Real-world tax & invoicing logic** — Bulgarian VAT treatments, gap-free legal
  numbering, dual-language documents, and digital signing.
- **Wiring an LLM to deterministic tools** — the language model orchestrates and
  drafts free text, but never touches the money math.

> ⚠️ **Status: early development.** The roadmap is written; the code is being
> built bottom-up, test-first. See [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) for
> the full phased plan. Today the repo is mostly scaffolding — don't expect a
> working invoice generator yet.

## What it does

You chat with it in your terminal:

> *"Draft an invoice for ACME for May."*

Behind that one sentence, Invoicely:

1. Pulls your Toggl time entries for the date range and groups them into line
   items (project + description → hours).
2. Translates the line descriptions EN → BG via DeepL (you can edit the result).
3. Looks up the right rates and legally-required VAT wording from your past
   contracts and invoices (a small RAG index over your own documents).
4. Computes VAT, totals, and any early-payment discount — in plain, tested
   Python, never by the LLM.
5. Shows you the actual computed invoice for confirmation.
6. On your OK, allocates the next legal invoice number, renders a dual-language
   PDF, digitally signs it, and saves both the PDF and a human-readable YAML
   record to your Proton Drive folder.

Planned features beyond the MVP: client-signed timesheets via Skribble, Revolut
payment reconciliation, expense & profitability tracking, and legally-correct
invoice cancellation & reissue.

## Usage

```bash
uv run python main.py       # run the app (thin shim -> invoicely.cli)
invoicely doctor            # environment / health smoke test
invoicely chat              # the terminal chat interface
invoicely reindex           # rebuild the RAG index over contracts & invoices
```

### Configuration

Secrets (API keys, signing-key password) live in a repo-local `.env`
(gitignored). Your business data — company legal info and per-client settings —
lives in the synced Drive folder so it travels with your invoices across
machines. The signing `.pfx` certificate is kept **outside** the synced folder.

The data folder location is set via `INVOICELY_DATA_DIR` (default
`~/ProtonDrive/Invoicely/`) and holds `config/`, `timesheets/`, `invoices/`,
`contracts/`, `rag/`, `payments/`, `expenses/`, and `history/`.

## Development

Python 3.13, managed with [`uv`](https://docs.astral.sh/uv/). The project is built
test-first and human-gated: for each step, the test suite is written and reviewed
*before* any implementation, and the accumulated suite is the safety net for later
refactoring. The full workflow and roadmap are in
[DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md).

```bash
uv run pytest               # run tests
uv run ruff check .         # lint
uv run mypy src             # type-check
uv add <package>            # add a dependency
```

Integrations are tested against recorded fixtures, never live APIs, and tests
always run against a throwaway temp data directory.

## License

Released under the [MIT License](LICENSE).
