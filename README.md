# B1 (Site.pro Accounting) integration for Flow Steward

<img src="icon.png" width="96" alt="B1 (Site.pro Accounting) integration for Flow Steward">

[![CI](https://img.shields.io/github/actions/workflow/status/Flow-Steward/ext-finance-b1/ci.yml?branch=main&label=CI)](https://github.com/Flow-Steward/ext-finance-b1/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/Flow-Steward/ext-finance-b1)](https://github.com/Flow-Steward/ext-finance-b1/releases/latest)

Automate B1 (Site.pro Accounting) with Flow Steward workflows and AI agents: invoices, clients, items and payments from your shop — without writing code.

This Flow Steward extension is an accounting integration for small businesses in Lithuania. It
connects B1 — now Site.pro Accounting (b1.lt) — to workflow automation through the B1 API, so
sales, purchases and payments reach the books without retyping.

## What is this

B1, now Site.pro Accounting, is Lithuanian online accounting software. This extension is a connector: it adds ready workflow steps to Flow Steward, and the
same steps are available as tools for AI agents. Learn more about Flow Steward at
[docs.flowsteward.org](https://docs.flowsteward.org).

## What you can automate

- Create sales invoices in Site.pro Accounting from orders in your shop — the client is found or created, no retyping.
- Record customer payments against sales from your bank or payment provider data.
- Enter supplier invoices as purchase invoices with their lines, once per supplier and number.
- Add new products from your catalogue as items, and read their prices and stock.
- Turn e-commerce orders into sales or stock write-offs.
- Keep clients from your CRM and Site.pro Accounting the same: find, create or update them.
- Get the profit-and-loss statement, balance or any other report as a file on a schedule.

## Why teams use it

- **No duplicate documents.** A sales invoice needs the transaction ID from your system, a purchase invoice its supplier and number, a payment its payment number: when Site.pro Accounting already has one, the step stops and creates nothing.
- **Exact amounts.** Amounts are plain decimals; where the API expects them multiplied by 100, 1000 or more, the step converts them and refuses a value it would have to round.
- **A change is never sent twice.** Writes are sent once and never retried; when the outcome is unclear, the step says so and asks you to check first.
- **A test run changes nothing.** Every write is skipped in test runs, so you can try a workflow safely.
- **The whole API.** Each of the 600 operations documented in the B1 API has its own step.
- **The key stays secret.** It is stored encrypted, travels only in the API header and is removed from everything the steps return.

## What's inside

Everyday steps:

- **Test the connection** — checks the API key in one read.
- **Find a client**, **Find or create a client** — one exact match by code, VAT code or e-mail; several matches stop the step.
- **Find an item**, **Find or create an item** — by code and barcode, with prices and stock.
- **Create a sales invoice with lines** — one sale per transaction ID.
- **Find a sale by transaction ID or number** — to check what is already there.
- **Create a purchase invoice with lines** — once per supplier and number.
- **Record a payment for a sale (checked for repeats)** — once per payment number.
- **Get a report (generate and wait)** — the report file is saved as a workflow file.

All 600 documented API operations are available as steps (610 steps in total): clients, items and reference data, sales, purchases and stock, bank and cash, documents, general ledger, personnel, salary, production, long-term assets, e-commerce and shop.

## Get started

1. In Flow Steward, open **Extensions → Catalog** and install **B1 (Site.pro Accounting)**.
2. In Site.pro Accounting, open **Settings → Integrations → API simplified**, add the service and copy the API key. In Flow Steward, open the extension's **Connection** page, add a connection named after the company and paste the key.
3. Press **Test connection**.
4. Build your first workflow, for example **Find or create a client** followed by **Create a sales invoice with lines**.

## Requirements

- A Site.pro Accounting plan that includes the API, with an active integration package.
- An "API simplified" key: read and write for writing steps, read-only if workflows only read. The e-commerce steps need a separate key from **Settings → Integrations → API for e-commerce**, in its own connection.
- For invoices: an employee, VAT rates and the items or services they sell, set up in Site.pro Accounting.
- Deletions take explicit IDs, at most 50 at a time. Deletions and 23 irreversible accounting actions (salary records, declarations, settlements, confirmations, stock-taking, write-offs and others) cannot be undone; try them on a test company first.
- Flow Steward 0.9.16 or later.

## FAQ

**How do I create invoices in Site.pro Accounting (B1) automatically from my online shop?**
Use **Find or create a client** and then **Create a sales invoice with lines**, with the order number as the transaction ID. A repeated order with the same ID stops the step instead of creating a second invoice.

**Can I record bank payments in B1 automatically?**
Yes. **Record a payment for a sale (checked for repeats)** records a bank payment for an existing sale and stops when a transaction with the same payment number is already there.

**Can I use a read-only B1 API key?**
Yes, for reading. A read-only key passes the connection test, but writing steps fail with an authorization error.

**Can I connect several companies?**
Yes. Each company and API key is a separate connection in the project.

**Can I export reports from Site.pro Accounting to a file?**
Yes. **Get a report (generate and wait)** generates the report and saves its file in the workflow, ready to e-mail or archive.

## In your language

B1 (Site.pro Accounting) integracija su Flow Steward automatizuoja buhalterinę apskaitą Lietuvoje: sąskaitas faktūras, klientus, prekes ir banko mokėjimus galima perkelti iš el. parduotuvės ar CRM be rankinio darbo. Plėtinys jungiasi per B1 API, ir kiekvienas iš 600 dokumentuotų API veiksmų turi savo žingsnį.

## Links

- [Flow Steward documentation](https://docs.flowsteward.org)
- [Flow Steward extension catalog](https://github.com/Flow-Steward/extensions)
- [Issues](https://github.com/Flow-Steward/ext-finance-b1/issues)
- [Site.pro Accounting API documentation](https://site.pro/My-Accounting/doc/api)

## For developers

The contracts and pages are generated from the facts taken from the vendor's documentation
(`tests/reference/b1_api.json`, `tests/reference/plan.py`); do not edit them by hand.

```bash
python3 tests/reference/build_contracts.py   # regenerate contracts and pages
```

From a Flow Steward checkout:

```bash
./flow-steward extensions test flowsteward.b1 --root <parent>
./core/entrypoints/cli/scripts/lint.sh --checks extension-static,extension-tests --extension-root <abs path>
```

B1, Site.pro and their marks belong to their owner; see [BRANDING.md](BRANDING.md).
