"""Every documented endpoint: its step id, its title and when it ships.

The rules hold for all 600 endpoints — released or not — so the identifiers of later
releases are fixed now and cannot drift when the documentation changes:

* operation_id: the path, ``/`` and ``-`` written as ``_``
  (``client/client-addresses/create`` → ``client_client_addresses_create``);
* title: a verb first, then the object — singular for one record (get, create,
  update), plural for lists and deletions (which take several ids); reports are
  "Generate the … report"; ``TITLES`` names the endpoints the rule does not fit, and
  ``QUALIFIERS`` tells apart objects of the same name in different groups;
* release: ``0.1.0`` (this release), ``0.2.0`` (planned), ``after-live`` (planned
  after a check against a live company), each with the reason.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

#: Writes in 0.1.0: what everyday sales, purchases, clients, items and payments need.
EVERYDAY_WRITES = frozenset(
    {
        "clients/create",
        "clients/update",
        "client/client-addresses/create",
        "client/client-addresses/update",
        "client/client-contacts/create",
        "client/client-contacts/update",
        "client/client-bank-accounts/create",
        "client/client-bank-accounts/update",
        "reference-book/items/create",
        "reference-book/items/update",
        "reference-book/item-groups/create",
        "reference-book/item-groups/update",
        "reference-book/measurement-units/create",
        "reference-book/measurement-units/update",
        "warehouse/sales/create",
        "warehouse/sales/update",
        "warehouse/sales/update-vat",
        "warehouse/sale-items/create",
        "warehouse/sale-items/create-simple",
        "warehouse/sale-items/update",
        "warehouse/purchases/create",
        "warehouse/purchases/update",
        "warehouse/purchase-items/create",
        "warehouse/purchase-items/update",
        "warehouse/sale-files/create",
        "warehouse/purchase-files/create",
        "bank/sale-invoice/payment",
        "bank/transactions/create",
        "bank/transaction-entries/create",
        "e-commerce/orders/create",
        "e-commerce/orders/create-sale",
        "e-commerce/order-items/create",
        "shop/orders/add",
    }
)
#: Irreversible or wide-reaching actions: only after a check against a live company.
AFTER_LIVE_ACTIONS = frozenset(
    {
        "declaration/generations/generate-ffdata",
        "general-ledger/settlements/settle",
        "warehouse/internal-movements/confirm",
        "warehouse/purchases/calculate-overhead-costs",
        "warehouse/purchases/reset-overhead-costs",
        "warehouse/stock-taking/generate",
        "warehouse/stock-taking-items/set-actual-quantity",
        "e-commerce/orders/create-write-off",
        "general-ledger/financial-accountability-articles/link",
    }
)
#: Reads that do something besides reading: planned, not in 0.1.0.
READ_LIKE_WRITES = frozenset({"warehouse/sale-reports/generate"})

#: Titles the rule does not fit.
TITLES: dict[str, str] = {
    "account/file-storage/upload": "Upload a file to a sale or purchase (file storage)",
    "bank/sale-invoice/payment": "Record a bank payment for a sale invoice",
    "cash-register/sales/add": "Add a cash register sale",
    "client/sales/balance": "Get a client's sales balance",
    "client/item-prices/list": "List client item prices",
    "declaration/generations/generate-ffdata": "Generate a declaration file (FFData)",
    "e-commerce/items/stock": "Get e-commerce item stock",
    "e-commerce/orders/create-sale": "Create a sale from an e-commerce order",
    "e-commerce/orders/create-write-off": "Create a write-off from an e-commerce order",
    "general-ledger/financial-accountability-articles/link": (
        "Link a financial accountability article"
    ),
    "general-ledger/settlements/settle": "Settle general ledger rows",
    "general-ledger-cards/items/history-list": "List the history of general ledger card items",
    "shop/invoices/get-upd": "Get a shop UPD invoice PDF",
    "shop/invoices/get": "Get a shop invoice PDF",
    "shop/orders/add": "Add a shop order",
    "shop/products/get": "Get a shop product file",
    "shop/delivery-acceptance-acts/get": "Get a shop delivery-acceptance act",
    "warehouse/cash-register-sales/receipt-create": "Create a sale from a cash register receipt",
    "warehouse/delivery-acceptance-acts/get-sale": "Get a sale's delivery-acceptance act PDF",
    "warehouse/internal-movements/confirm": "Confirm internal movements",
    "warehouse/invoices/get-sale": "Get a sale invoice file",
    "warehouse/invoices/get-upd": "Get a sale's UPD file",
    "warehouse/purchases/calculate-overhead-costs": "Calculate a purchase's overhead costs",
    "warehouse/purchases/reset-overhead-costs": "Reset a purchase's overhead costs",
    "warehouse/sale-items/create-simple": "Create a sale item (simple, FIFO write-off)",
    "warehouse/sale-reports/generate": "Generate a sale report file",
    "warehouse/sales/update-vat": "Update a sale's VAT amount",
    "warehouse/stock-taking-items/list-by-barcode": "List stock-taking items by barcode",
    "warehouse/stock-taking-items/set-actual-quantity": "Set a stock-taking item's actual quantity",
    "warehouse/stock-taking/generate": "Generate stock-taking items",
    "warehouse/temp-files/add-purchase": "Upload a purchase document to file storage",
    "warehouse/temp-files/add-sale": "Upload a sale document to file storage",
    "warehouse/temp-files/get-recognized-data": "Get recognized data of a stored file",
    "reports/get": "Get a generated report file",
}
#: Group words that tell apart objects of the same name.
QUALIFIERS: dict[str, str] = {
    "bank": "bank",
    "cash-flow": "cash",
    "general-ledger": "general ledger",
    "general-ledger-cards": "general ledger card",
    "reference-book": "",
    "document": "document",
    "e-commerce": "e-commerce",
    "shop": "shop",
    "personnel": "personnel",
    "production": "production",
    "salary": "salary",
    "warehouse": "warehouse",
    "cash-register": "cash register",
    "declaration": "declaration",
    "traces": "",
    "long-term-asset": "long-term asset",
    "client": "",
    "bi": "BI",
    "account": "",
}
_IRREGULAR = {
    "addresses": "address",
    "statuses": "status",
    "series": "series",
    "analyses": "analysis",
    "news": "news",
    "data": "data",
    "classes": "class",
    "taxes": "tax",
    "boxes": "box",
}
_VERBS = {
    "list": "List",
    "get": "Get",
    "create": "Create",
    "update": "Update",
    "delete": "Delete",
}
_WRITE_ACTIONS = {"create", "update", "delete"}


def singular(word: str) -> str:
    if word in _IRREGULAR:
        return _IRREGULAR[word]
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("sses", "xes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def operation_id(path: str) -> str:
    return path.strip("/").replace("/", "_").replace("-", "_")


def _article(text: str) -> str:
    return ("an " if text[:1] in "aeiou" else "a ") + text


@cache
def endpoints() -> tuple[dict[str, Any], ...]:
    data = json.loads((HERE / "b1_api.json").read_text(encoding="utf-8"))
    return tuple(data["endpoints"])


def _report_title(entry: dict[str, Any]) -> str:
    name = entry["description"].strip().rstrip(".")
    name = re.sub(r"\s+report$", "", name, flags=re.IGNORECASE)
    name = name[:1].lower() + name[1:] if not name[:2].isupper() else name
    return f"Generate the {name} report"


def _plain_title(entry: dict[str, Any], qualify: bool) -> str:
    path, action = entry["path"], entry["action"]
    resource = path.split("/")[-2] if path.count("/") >= 1 else path
    words = resource.replace("-", " ").split()
    if qualify and QUALIFIERS.get(entry["group"]):
        prefix = QUALIFIERS[entry["group"]]
        if not " ".join(words).startswith(prefix):
            words = [*prefix.split(), *words]
    plural = " ".join(words)
    one = " ".join([*words[:-1], singular(words[-1])])
    if entry.get("answers_file") and action == "get":
        return f"Get {_article(one)}"
    if any(h["field"] == "B1-File-Name" for h in entry["headers"]):
        return f"Upload {_article(one)}"
    verb = _VERBS[action]
    if action in {"list", "delete"}:
        return f"{verb} {plural}"
    return f"{verb} {_article(one)}"


@cache
def titles() -> dict[str, str]:
    """path -> title, unique over all endpoints."""
    plain: dict[str, str] = {}
    for entry in endpoints():
        path = entry["path"]
        if path in TITLES:
            plain[path] = TITLES[path]
        elif entry["group"] == "reports":
            plain[path] = _report_title(entry)
        else:
            plain[path] = _plain_title(entry, qualify=False)
    counts: dict[str, int] = {}
    for title in plain.values():
        counts[title] = counts.get(title, 0) + 1
    out: dict[str, str] = {}
    for entry in endpoints():
        path = entry["path"]
        title = plain[path]
        if counts[title] > 1 and path not in TITLES and entry["group"] != "reports":
            title = _plain_title(entry, qualify=True)
        out[path] = title
    seen: dict[str, str] = {}
    for path, title in out.items():
        if title in seen:
            raise ValueError(f"title {title!r} of {path} repeats {seen[title]}")
        seen[title] = path
    return out


def kind(entry: dict[str, Any]) -> str:
    """read, file (a read answering a file), report (a report task), report_get,
    upload, create, update, delete or other."""
    path, action = entry["path"], entry["action"]
    if entry["group"] == "reports":
        return "report_get" if path == "reports/get" else "report"
    if any(h["field"] == "B1-File-Name" for h in entry["headers"]):
        return "upload"
    if action in _WRITE_ACTIONS:
        return action
    if path in AFTER_LIVE_ACTIONS or path in READ_LIKE_WRITES:
        return "other"
    if (
        path in EVERYDAY_WRITES
        or path.endswith(("/payment", "/add", "-create"))
        or action
        in {
            "create-simple",
            "create-sale",
            "add-sale",
            "add-purchase",
            "update-vat",
        }
    ):
        return "create" if action != "update-vat" else "update"
    if entry["answers_file"]:
        return "file"
    return "read"


def release(entry: dict[str, Any]) -> tuple[str, str]:
    """(release, reason)."""
    path = entry["path"]
    k = kind(entry)
    if path in EVERYDAY_WRITES:
        return "0.1.0", "Everyday write."
    if k in {"read", "file", "report", "report_get"}:
        return "0.1.0", "Read: changes nothing in Site.pro Accounting."
    if k == "delete":
        return "after-live", "Deletion: planned after a check against a live company."
    if entry["group"] == "salary":
        return "after-live", "Salary: planned after a check against a live company."
    if path in AFTER_LIVE_ACTIONS:
        return "after-live", "Irreversible or wide action: planned after a live check."
    return "0.2.0", "Planned for 0.2.0."


@cache
def plan() -> tuple[dict[str, Any], ...]:
    names = titles()
    rows = []
    for entry in endpoints():
        ship, reason = release(entry)
        rows.append(
            {
                "path": entry["path"],
                "operation_id": operation_id(entry["path"]),
                "title": names[entry["path"]],
                "kind": kind(entry),
                "release": ship,
                "reason": reason,
            }
        )
    return tuple(rows)


__all__ = ["EVERYDAY_WRITES", "TITLES", "kind", "operation_id", "plan", "release", "titles"]
