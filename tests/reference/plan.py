"""Every documented endpoint: its step id, title, kind, danger and object count.

The rules hold for all 600 endpoints, each of them a step, so the identifiers are
fixed by rule and cannot drift when the documentation changes:

* operation_id: the path, ``/`` and ``-`` written as ``_``
  (``client/client-addresses/create`` → ``client_client_addresses_create``);
* title: a verb first, then the object — singular for one record (get, create,
  update), plural for lists and deletions (which take several ids); reports are
  "Generate the … report"; ``TITLES`` names the endpoints the rule does not fit, and
  ``QUALIFIERS`` tells apart objects of the same name in different groups;
* release: every endpoint is a step of 0.1.0; the reason says what kind of step;
* danger: deletions and the irreversible accounting actions (salary records,
  declarations, settlements, confirmations, overhead costs, stock-taking, write-offs,
  article links) are marked, so their steps take only explicit ids, say what they
  change in the accounting and come last in their group;
* objects: whether a write changes exactly ``one`` object (a refusal then means nothing
  was saved), ``several`` (a refusal says nothing about how far it got) or one object
  per given id (``by_ids``: one id → one, more → several).
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

#: The writes everyday sales, purchases, clients, items and payments need.
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
#: Irreversible or wide-reaching accounting actions: explicit ids, a plain warning.
IRREVERSIBLE_ACTIONS = frozenset(
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
#: Not a create, update or delete, yet sent as a write: it makes something on the
#: server (a generated file) and is not confirmed to be harmless.
READ_LIKE_WRITES = frozenset({"warehouse/sale-reports/generate"})
#: Writes that answer with a file (the declaration file is generated and returned).
FILE_ANSWER_ACTIONS = frozenset({"declaration/generations/generate-ffdata"})
#: Writes whose parameters name one object but which change several: documents with
#: their lines, allocations across a purchase's items, generated stock-taking lines.
SEVERAL_OBJECTS = frozenset(
    {
        "shop/orders/add",
        "e-commerce/orders/create",
        "e-commerce/orders/create-sale",
        "e-commerce/orders/create-write-off",
        "cash-register/sales/add",
        "warehouse/purchases/calculate-overhead-costs",
        "warehouse/purchases/reset-overhead-costs",
        "warehouse/stock-taking/generate",
    }
)
#: What each irreversible action changes in the accounting (one sentence each).
ACCOUNTING_EFFECTS: dict[str, str] = {
    "declaration/generations/generate-ffdata": (
        "Generates the declaration from the company's accounting data for the period; "
        "Site.pro Accounting may record the generation, and the step cannot undo it."
    ),
    "general-ledger/settlements/settle": (
        "Settles the given open general ledger rows against each other, so they no longer "
        "show as open; the step cannot undo it."
    ),
    "warehouse/internal-movements/confirm": (
        "Confirms the given internal movements, which moves their stock between "
        "warehouses in the accounting; the step cannot undo it."
    ),
    "warehouse/purchases/calculate-overhead-costs": (
        "Allocates the purchase's overhead costs across its items, changing their cost and "
        "the related ledger entries; the step cannot undo it (Reset a purchase's overhead "
        "costs reverses the allocation)."
    ),
    "warehouse/purchases/reset-overhead-costs": (
        "Reverses the purchase's overhead cost allocation and its ledger entries, changing "
        "the cost of its items; the step cannot undo it."
    ),
    "warehouse/stock-taking/generate": (
        "Generates the stock-taking document's item lines from its filters; the step cannot "
        "undo it."
    ),
    "warehouse/stock-taking-items/set-actual-quantity": (
        "Overwrites the counted quantity of the item in the stock-taking document, which "
        "decides the stock differences it books; the step cannot undo it."
    ),
    "e-commerce/orders/create-write-off": (
        "Creates a write-off of the order's goods, reducing the stock in the accounting; "
        "the step cannot undo it."
    ),
    "general-ledger/financial-accountability-articles/link": (
        "Links the financial accountability article to the account, which changes how the "
        "financial statements group it; the step cannot undo it."
    ),
}
_SALARY_EFFECT = (
    "Changes the payroll data the company's salaries, payslips and salary declarations "
    "are calculated from; the step cannot undo it."
)

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
    upload, create, update, delete, action (another write) or action_file (a write
    answering a file)."""
    path, action = entry["path"], entry["action"]
    if entry["group"] == "reports":
        return "report_get" if path == "reports/get" else "report"
    if any(h["field"] == "B1-File-Name" for h in entry["headers"]):
        return "upload"
    if action in _WRITE_ACTIONS:
        return action
    if path in FILE_ANSWER_ACTIONS:
        return "action_file"
    if path in IRREVERSIBLE_ACTIONS or path in READ_LIKE_WRITES:
        return "action"
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


WRITE_KINDS = frozenset({"create", "update", "upload", "delete", "action", "action_file"})


def danger(entry: dict[str, Any]) -> str:
    """ "delete", "irreversible" or "" (an ordinary step)."""
    k = kind(entry)
    if k == "delete":
        return "delete"
    if entry["path"] in IRREVERSIBLE_ACTIONS or (entry["group"] == "salary" and k in WRITE_KINDS):
        return "irreversible"
    return ""


def accounting_effect(entry: dict[str, Any]) -> str:
    """The sentence an irreversible step's description carries."""
    if entry["path"] in ACCOUNTING_EFFECTS:
        return ACCOUNTING_EFFECTS[entry["path"]]
    if entry["group"] == "salary":
        return _SALARY_EFFECT
    return ""


_LIST_KINDS = {"decimal_list", "json", "object", "object_list"}


def objects(entry: dict[str, Any]) -> str:
    """How many objects a write changes: "one", "several" or "by_ids" (see the module).

    "several" is the default; "one" only when the parameters can name nothing but one
    object: plain values only, no list or nested record, and not a known exception.
    """
    import params  # the sibling module; plan is imported from the builder and tests

    k = kind(entry)
    if k not in WRITE_KINDS:
        return ""
    if k == "upload":
        return "one"  # one file to the record named in its headers
    nodes = params.tree(entry["params"])
    if k == "delete":
        return (
            "by_ids" if any(n["kind"] in {"decimal_list", "object_list"} for n in nodes) else "one"
        )
    if entry["path"] in SEVERAL_OBJECTS or entry["path"] in READ_LIKE_WRITES:
        return "several"
    if any(n["kind"] in _LIST_KINDS for n in nodes):
        return "several"
    return "one"


def release(entry: dict[str, Any]) -> tuple[str, str]:
    """(release, reason): every endpoint is a step of 0.1.0."""
    k = kind(entry)
    if k in {"read", "file", "report", "report_get"}:
        return "0.1.0", "Read: changes nothing in Site.pro Accounting."
    flag = danger(entry)
    if flag == "delete":
        return "0.1.0", "Deletion: explicit ids only; it cannot be undone."
    if flag == "irreversible":
        return "0.1.0", "Irreversible accounting action: explicit inputs; it cannot be undone."
    if entry["path"] in EVERYDAY_WRITES:
        return "0.1.0", "Everyday write."
    return "0.1.0", "Write."


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
                "danger": danger(entry),
                "objects": objects(entry),
                "release": ship,
                "reason": reason,
            }
        )
    return tuple(rows)


__all__ = [
    "EVERYDAY_WRITES",
    "IRREVERSIBLE_ACTIONS",
    "SEVERAL_OBJECTS",
    "TITLES",
    "WRITE_KINDS",
    "accounting_effect",
    "danger",
    "kind",
    "objects",
    "operation_id",
    "plan",
    "release",
    "titles",
]
