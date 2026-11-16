"""The everyday steps (runtime/composites.py): names, descriptions, inputs and outputs."""

from __future__ import annotations

from typing import Any

ISO_DATE = r"^\d{4}-\d{2}-\d{2}$"
DECIMAL = ["number", "string"]
NULL_TEXT = ["string", "null"]
NULL_INT = ["integer", "null"]

WARNINGS = {
    "name": "warnings",
    "value_type": "array",
    "schema": {
        "type": "array",
        "items": {"type": "string"},
        "description": "What the step could not do fully or what to check.",
    },
}
REPEATS = (
    "A step that fails half-way says which records it created, with their ids, and deletes nothing."
)


def text(
    name: str,
    title: str,
    description: str,
    *,
    max_length: int = 255,
    required: bool = False,
    pattern: str | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "string",
        "title": title,
        "description": description,
        "maxLength": max_length,
    }
    if pattern:
        schema["pattern"] = pattern
    return {"name": name, "value_type": "text", "required": required, "schema": schema}


def date(name: str, title: str, description: str, *, required: bool = False) -> dict[str, Any]:
    return text(
        name,
        title,
        description + " YYYY-MM-DD.",
        max_length=10,
        required=required,
        pattern=ISO_DATE,
    )


def number(name: str, title: str, description: str, *, required: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "value_type": "text",
        "required": required,
        "schema": {"type": DECIMAL, "title": title, "description": description},
    }


def whole(name: str, title: str, description: str, *, required: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "value_type": "integer",
        "required": required,
        "schema": {"type": "integer", "minimum": 1, "title": title, "description": description},
    }


def flag(name: str, title: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "value_type": "boolean",
        "required": False,
        "schema": {"type": "boolean", "title": title, "description": description},
    }


def out(name: str, value_type: str, kind: Any, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "value_type": value_type,
        "schema": {"type": kind, "description": description},
    }


def record(name: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "value_type": "object",
        "schema": {
            "type": ["object", "null"],
            "additionalProperties": True,
            "description": description,
        },
    }


def lines(item: dict[str, Any], description: str, placeholder: str) -> dict[str, Any]:
    return {
        "name": "lines",
        "value_type": "array",
        "required": True,
        "schema": {
            "type": "array",
            "title": "Lines",
            "description": description,
            "minItems": 1,
            "maxItems": 200,
            "items": item,
        },
        "placeholder": placeholder,
    }


def _obj(fields: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": fields,
    }


def _i(description: str) -> dict[str, Any]:
    return {"type": "integer", "description": description}


def _n(description: str) -> dict[str, Any]:
    return {"type": DECIMAL, "description": description}


def _t(description: str, max_length: int = 255) -> dict[str, Any]:
    return {"type": "string", "maxLength": max_length, "description": description}


CLIENT_KEYS = [
    text("code", "Client code", "The client's company or personal code, exactly.", max_length=50),
    text("vat_code", "VAT code", "The client's VAT code, exactly.", max_length=50),
    text("email", "E-mail", "The client's e-mail, exactly.", max_length=255),
]
ITEM_KEYS = [
    text("code", "Item code", "The item's code, exactly.", max_length=100),
    text("barcode", "Barcode", "The item's barcode, exactly.", max_length=100),
]
REPORT_OUTPUTS = [
    out("ready", "boolean", "boolean", "True when the report file was saved."),
    out("task_id", "integer", NULL_INT, "The report task's ID."),
    {
        "name": "file",
        "value_type": "artifact_handle",
        "schema": {"type": NULL_TEXT, "description": "The report, as a workflow file."},
    },
    out("file_name", "text", NULL_TEXT, "Its file name."),
    out("mime_type", "text", NULL_TEXT, "Its type."),
    out("size_bytes", "integer", NULL_INT, "Its size."),
    WARNINGS,
]


def steps() -> list[dict[str, Any]]:
    return [
        {
            "operation_id": "test_connection",
            "display_name": "Test the connection",
            "kind": "source",
            "calls": ["reference-book/currencies/list"],
            "description": "Checks the API key by listing ten currencies.",
            "inputs": [],
            "outputs": [
                out("connected", "boolean", "boolean", "True when the key works."),
                WARNINGS,
            ],
        },
        {
            "operation_id": "find_client",
            "display_name": "Find a client",
            "kind": "source",
            "calls": ["clients/list"],
            "description": (
                "Finds the one client whose code, VAT code and e-mail (those given) match "
                "exactly. Several matches stop the step with a conflict."
            ),
            "inputs": CLIENT_KEYS,
            "outputs": [
                out("found", "boolean", "boolean", "True when a client matches."),
                record("client", "The client, as Site.pro Accounting lists it."),
                WARNINGS,
            ],
        },
        {
            "operation_id": "find_or_create_client",
            "display_name": "Find or create a client",
            "kind": "action",
            "calls": ["clients/list", "clients/create"],
            "description": (
                "Finds the client by its code, VAT code and e-mail (those given, all exactly); "
                "creates it only when none matches. Several matches stop the step with a "
                "conflict and nothing is created."
            ),
            "inputs": [
                *CLIENT_KEYS,
                text("name", "Name", "The name of a new client.", max_length=255),
                text("short_name", "Short name", "The short name of a new client.", max_length=100),
                whole(
                    "location_id",
                    "Location ID",
                    "The location (country) ID of a new client in Site.pro Accounting.",
                ),
                flag("is_juridical", "Company", "A new client is a company, not a person."),
                text("phone_number", "Phone", "The phone of a new client.", max_length=50),
                flag("is_supplier", "Supplier", "A new client is also a supplier."),
            ],
            "outputs": [
                out("client_id", "integer", NULL_INT, "The client's ID."),
                out("created", "boolean", "boolean", "True when this step created it."),
                record("client", "The client found, or null when created."),
                WARNINGS,
            ],
        },
        {
            "operation_id": "find_item",
            "display_name": "Find an item",
            "kind": "source",
            "calls": ["reference-book/items/list"],
            "description": (
                "Finds the one item whose code and barcode (those given) match exactly, with its "
                "prices and stock. Several matches stop the step with a conflict."
            ),
            "inputs": ITEM_KEYS,
            "outputs": [
                out("found", "boolean", "boolean", "True when an item matches."),
                record("item", "The item, as Site.pro Accounting lists it."),
                WARNINGS,
            ],
        },
        {
            "operation_id": "find_or_create_item",
            "display_name": "Find or create an item",
            "kind": "action",
            "calls": ["reference-book/items/list", "reference-book/items/create"],
            "description": (
                "Finds the item by its code and barcode (those given, exactly); creates it only "
                "when none matches. Several matches stop the step with a conflict."
            ),
            "inputs": [
                *ITEM_KEYS,
                text("name", "Name", "The name of a new item.", max_length=255),
                whole(
                    "attribute_id",
                    "Attribute ID",
                    "The item attribute (product or service) ID of a new item.",
                ),
                whole("measurement_unit_id", "Unit ID", "The unit of measure ID of a new item."),
                whole("group_id", "Group ID", "The item group ID of a new item."),
                number("price_without_vat", "Price without VAT", "The price of a new item."),
                number("vat_rate", "VAT rate", "The VAT rate of a new item, in percent."),
                number("price_with_vat", "Price with VAT", "The price with VAT of a new item."),
            ],
            "outputs": [
                out("item_id", "integer", NULL_INT, "The item's ID."),
                out("created", "boolean", "boolean", "True when this step created it."),
                record("item", "The item found, or null when created."),
                WARNINGS,
            ],
        },
        {
            "operation_id": "create_sales_invoice",
            "display_name": "Create a sales invoice with lines",
            "kind": "action",
            "calls": [
                "warehouse/sales/list",
                "warehouse/sales/create",
                "warehouse/sale-items/create-simple",
            ],
            "description": (
                "Creates a sale document and its lines (quantitatively accounted items are "
                "written off FIFO). The transaction ID from your system is required: when "
                "Site.pro Accounting already has a sale with it, the step stops with a conflict "
                "and creates nothing. " + REPEATS
            ),
            "inputs": [
                text(
                    "transaction_id",
                    "Transaction ID",
                    "The sale's ID in your system (transactionId); it keeps reruns from "
                    "creating the sale twice.",
                    max_length=100,
                    required=True,
                ),
                date("sale_date", "Sale date", "The sale date.", required=True),
                date("pay_until", "Pay until", "The payment due date."),
                whole("warehouse_id", "Warehouse ID", "The warehouse.", required=True),
                whole("client_id", "Client ID", "The client.", required=True),
                whole(
                    "operation_type_id", "Operation type ID", "The operation type.", required=True
                ),
                whole("employee_id", "Employee ID", "The employee issuing it.", required=True),
                text(
                    "series",
                    "Series",
                    "The series; leave series and number empty to have them generated.",
                    max_length=50,
                ),
                text("number", "Number", "The number, with the series.", max_length=50),
                whole("vat_rate_id", "VAT rate ID", "The VAT rate of the document."),
                text("notes", "Notes", "Notes.", max_length=1000),
                text(
                    "order_number_client",
                    "Client's order number",
                    "The client's order number in your system.",
                    max_length=100,
                ),
                lines(
                    _obj(
                        {
                            "item_id": _i("Item ID."),
                            "quantity": _n("Quantity, up to 3 decimals."),
                            "price_without_vat": _n("Price without VAT, up to 4 decimals."),
                            "price_with_vat": _n("Price with VAT; used instead when given."),
                            "vat_rate": _n("VAT rate in percent."),
                            "discount_rate": _n("Discount in percent."),
                            "vat_classification_id": _i("VAT classification ID."),
                            "warehouse_id": _i("Warehouse; default the document's."),
                            "postscript_text": _t("Postscript for the sale report.", 500),
                        },
                        ["item_id", "quantity", "price_without_vat"],
                    ),
                    "The lines, 1 to 200: item_id, quantity, price_without_vat and optionally "
                    "price_with_vat, vat_rate, discount_rate, vat_classification_id, "
                    "warehouse_id, postscript_text.",
                    '[{"item_id":1,"quantity":2,"price_without_vat":"10.50","vat_rate":21}]',
                ),
            ],
            "outputs": [
                out("sale_id", "integer", NULL_INT, "The sale's ID."),
                {
                    "name": "line_ids",
                    "value_type": "array",
                    "schema": {"type": "array", "description": "The lines' IDs."},
                },
                out("transaction_id", "text", NULL_TEXT, "The transaction ID sent."),
                WARNINGS,
            ],
        },
        {
            "operation_id": "find_sale",
            "display_name": "Find a sale by transaction ID or number",
            "kind": "source",
            "calls": ["warehouse/sales/list"],
            "description": "Finds the one sale with this transaction ID, or series and number.",
            "inputs": [
                text(
                    "transaction_id",
                    "Transaction ID",
                    "The sale's ID in your system.",
                    max_length=100,
                ),
                text("series", "Series", "The series.", max_length=50),
                text("number", "Number", "The number.", max_length=50),
            ],
            "outputs": [
                out("found", "boolean", "boolean", "True when a sale matches."),
                record("sale", "The sale, as Site.pro Accounting lists it."),
                WARNINGS,
            ],
        },
        {
            "operation_id": "create_purchase_invoice",
            "display_name": "Create a purchase invoice with lines",
            "kind": "action",
            "calls": [
                "warehouse/purchases/list",
                "warehouse/purchases/create",
                "warehouse/purchase-items/create",
            ],
            "description": (
                "Creates a purchase document and its lines, without discounts. When Site.pro "
                "Accounting already has this supplier's purchase with the same number (and "
                "series), the step stops with a conflict and creates nothing. " + REPEATS
            ),
            "inputs": [
                whole("supplier_id", "Supplier ID", "The supplier (a client).", required=True),
                text(
                    "number",
                    "Number",
                    "The supplier's document number.",
                    max_length=50,
                    required=True,
                ),
                text("series", "Series", "The supplier's document series.", max_length=50),
                date("purchase_date", "Purchase date", "The purchase date.", required=True),
                date("pay_until", "Pay until", "The payment due date."),
                whole("warehouse_id", "Warehouse ID", "The warehouse.", required=True),
                whole(
                    "operation_type_id", "Operation type ID", "The operation type.", required=True
                ),
                whole("currency_id", "Currency ID", "The currency.", required=True),
                whole("employee_id", "Employee ID", "The employee.", required=True),
                whole("vat_rate_id", "VAT rate ID", "The VAT rate of the document."),
                number("vat", "VAT", "The document's VAT amount, 2 decimals."),
                text("notes", "Notes", "Notes.", max_length=1000),
                lines(
                    _obj(
                        {
                            "item_id": _i("Item ID."),
                            "quantity": _n("Quantity, up to 3 decimals."),
                            "price_without_vat": _n("Price without VAT, up to 4 decimals."),
                            "price_with_vat": _n("Price with VAT, up to 4 decimals."),
                            "vat_rate": _n("VAT rate in percent, up to 2 decimals."),
                            "vat_classification_id": _i("VAT classification ID."),
                            "warehouse_id": _i("Warehouse; default the document's."),
                            "notes": _t("Line notes.", 500),
                        },
                        ["item_id", "quantity", "price_without_vat", "price_with_vat", "vat_rate"],
                    ),
                    "The lines, 1 to 200: item_id, quantity, price_without_vat, price_with_vat, "
                    "vat_rate and optionally vat_classification_id, warehouse_id, notes.",
                    '[{"item_id":1,"quantity":3,"price_without_vat":"3.7651",'
                    '"price_with_vat":"4.5558","vat_rate":21}]',
                ),
            ],
            "outputs": [
                out("purchase_id", "integer", NULL_INT, "The purchase's ID."),
                {
                    "name": "line_ids",
                    "value_type": "array",
                    "schema": {"type": "array", "description": "The lines' IDs."},
                },
                WARNINGS,
            ],
        },
        {
            "operation_id": "record_sale_payment",
            "display_name": "Record a payment for a sale (checked for repeats)",
            "kind": "action",
            "calls": ["bank/transactions/list", "bank/sale-invoice/payment"],
            "description": (
                "Records a bank payment for an existing sale. When Site.pro Accounting already "
                "has a bank transaction with this payment number, the step stops with a "
                "conflict and records nothing."
            ),
            "inputs": [
                whole("sale_id", "Sale ID", "The sale paid.", required=True),
                text(
                    "payment_id",
                    "Payment number",
                    "The bank payment's unique number.",
                    max_length=100,
                    required=True,
                ),
                date("payment_date", "Payment date", "The bank record date.", required=True),
                number("amount", "Amount", "The amount paid, 2 decimals.", required=True),
                number("tax", "Tax", "The tax amount, 2 decimals.", required=True),
                text(
                    "currency",
                    "Currency",
                    "The currency code, for example EUR.",
                    max_length=3,
                    required=True,
                ),
                text("purpose", "Purpose", "The payment note.", max_length=500, required=True),
            ],
            "outputs": [
                out("transaction_id", "text", NULL_TEXT, "The bank transaction's ID."),
                out("payment_id", "text", NULL_TEXT, "The payment number sent."),
                WARNINGS,
            ],
        },
        {
            "operation_id": "get_report",
            "display_name": "Get a report (generate and wait)",
            "kind": "source",
            "calls": ["reports/*", "reports/get"],
            "description": (
                "Generates one of the reports and waits for its file, saving it as a workflow "
                "file; when it is not ready in time, returns its task ID for Get a generated "
                "report file. Site.pro Accounting offers its reports as a beta."
            ),
            "inputs": [
                text(
                    "report",
                    "Report",
                    "The step ID of the Generate … report step, for "
                    "example reports_general_ledger_general_ledger_trial_balance.",
                    max_length=120,
                    required=True,
                ),
                {
                    "name": "parameters",
                    "value_type": "object",
                    "required": False,
                    "schema": {
                        "type": "object",
                        "title": "Parameters",
                        "description": "That report's inputs, as on its own step.",
                    },
                },
            ],
            "outputs": REPORT_OUTPUTS,
        },
    ]


__all__ = ["steps"]
