# B1 (Site.pro Accounting) for Flow Steward

Workflow steps for B1, now Site.pro Accounting — the Lithuanian online accounting software —
through its API ([documentation](https://site.pro/My-Accounting/doc/api)).

- **Everyday steps**: find or create a client or an item, create a sales or purchase invoice
  with its lines, record a payment for a sale (checked for repeats), find a sale, get a
  report (generate and wait), test the connection.
- **One step for every one of the 600 documented operations**: clients, items and reference
  data, sales, purchases and stock, bank and cash, documents, general ledger, personnel,
  salary, production, long-term assets, e-commerce and shop — reads with paging and filters,
  file downloads, reports, creates, updates, uploads and deletions.
- **Steps that cannot be undone** — 117 deletions and 23 irreversible accounting actions
  (salary records, declarations, settlements, confirmations, overhead costs, stock-taking,
  write-offs, article links) — take explicit IDs only (a deletion at most 50), say in their
  description what they change, and come last in their section. Try them on a test company
  before using them on a working one.

Amounts are plain decimals: where the API takes an amount multiplied by 100, 1000, 10000 or
1000000, the step converts it, and refuses a value with more decimals than that allows.
Writes are sent once and never retried; when the outcome is unclear, the step says so and
asks to check Site.pro Accounting first. The extension's **B1 API** pages describe every step
by area, and the **Coverage** page sums them up.

## Setup

1. In Site.pro Accounting, open **Settings → Integrations → API simplified**, add the service
   and copy the API key (the API is available on plans that include it). The e-commerce steps
   need a separate key from **API for e-commerce**.
2. In Flow Steward, open the extension's **Connection** page, add a connection with that key
   and press **Test connection**.

The steps connect only to `https://site.pro/My-Accounting/api`; the key travels only in the
`B1-Api-Key` header and is removed from everything the steps return.

## Development

```bash
python3 tests/reference/build_contracts.py   # regenerate contracts and pages
python3 -m pytest -q tests                   # tests, no network
```

`tests/reference/b1_api.json` holds the facts taken from the vendor's documentation
(`extract_reference.py`); `tests/reference/plan.py` fixes the step id, title, kind, danger
and object count of every documented operation.
