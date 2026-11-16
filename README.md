# B1 (Site.pro Accounting) for Flow Steward

Workflow steps for B1, now Site.pro Accounting — the Lithuanian online accounting software —
through its API ([documentation](https://site.pro/My-Accounting/doc/api)).

- **Everyday steps**: find or create a client or an item, create a sales or purchase invoice
  with its lines, record a payment for a sale (checked for repeats), find a sale, get a
  report (generate and wait), test the connection.
- **One step per documented operation** for every read — clients, items and reference data,
  sales, purchases and stock, bank and cash, documents, general ledger, personnel, salary,
  production, long-term assets, e-commerce and shop — with paging and filters, for every file
  download and every report, and for the writes of everyday sales, purchases, clients,
  items, payments and shop orders.

Amounts are plain decimals: where the API takes an amount multiplied by 100, 1000, 10000 or
1000000, the step converts it, and refuses a value with more decimals than that allows. The
extension's **Coverage** page says which operations have a step in this version and which come
later.

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
(`extract_reference.py`); `tests/reference/plan.py` fixes the step id, title and release of
every documented operation.
