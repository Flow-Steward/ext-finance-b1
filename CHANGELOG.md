# Changelog

## 0.1.0 — 2026-11-16

- First release: steps for B1 (Site.pro Accounting) through its API.
- Everyday steps: find or create a client or an item; create a sales invoice or a purchase
  invoice with its lines, refused when the same sale or purchase is already there; record a
  payment for a sale, checked for repeats; find a sale; get a report, generated and waited for.
- One step for every one of the 600 documented operations: reads, file downloads, reports,
  creates, updates, uploads and deletions.
- Deletions take explicit IDs only, at most 50 per run, and irreversible accounting actions
  (salary records, declarations, settlements, confirmations, overhead costs, stock-taking,
  write-offs, article links) say what they change; neither is ever retried, and test runs
  send nothing.
- Amounts are plain decimals, converted where the API expects them multiplied; lists page
  with a cursor or page number and take filters on the documented fields.
- The key is sent only to https://site.pro and is removed from everything the steps return.
