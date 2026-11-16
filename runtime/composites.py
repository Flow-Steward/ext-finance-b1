"""Everyday steps: several documented operations in one step.

Searches are strict: every key given must match exactly, and more than one match
stops the step with a conflict. A record is created only when nothing matches. A
step that writes several records and fails half-way says exactly what was created,
with the ids, and never deletes anything to undo it.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from . import errors, files, values
from .context import Context
from .errors import ExtensionError, invalid
from .generic import registry, request_body
from .params import body
from .transport import MIN_CALL_WINDOW_SECONDS, DeadlineReached

SEARCH_ROWS = 10
MAX_LINES = 200
#: How long Get a report waits between asking for the file.
REPORT_POLL_SECONDS = 15.0


# -- shared ---------------------------------------------------------------------------------


def _find(context: Context, path: str, rules: list[tuple[str, str]]) -> list[Mapping[str, Any]]:
    """Records of a list whose fields equal the given values exactly (at most 10)."""
    answer = context.transport.read(
        path,
        {
            "rows": SEARCH_ROWS,
            "filters": {
                "groupOp": "AND",
                "rules": [{"field": f, "op": "eq", "data": v} for f, v in rules],
            },
        },
    )
    data = answer.get("data")
    rows = data if isinstance(data, list) else []
    # The filter is applied by Site.pro Accounting; each value is checked again here.
    return [
        row
        for row in rows
        if isinstance(row, Mapping) and all(str(row.get(f) or "") == v for f, v in rules)
    ]


def _one(found: list[Mapping[str, Any]], what: str, keys: str) -> Mapping[str, Any] | None:
    if len(found) > 1:
        ids = ", ".join(str(r.get("id")) for r in found[:5])
        raise errors.no_effect(
            errors.CONFLICT,
            f"{len(found)} {what}s match {keys} (ids {ids}); it does not name one {what}",
        )
    return found[0] if found else None


def _keys(operation_input: Mapping[str, Any], mapping: Mapping[str, str]) -> list[tuple[str, str]]:
    rules = []
    for name, field in mapping.items():
        value = values.text(operation_input.get(name), name, max_length=255)
        if value is not None:
            rules.append((field, value))
    if not rules:
        raise invalid(f"Give at least one of: {', '.join(mapping)}")
    return rules


def _created_id(answer: Mapping[str, Any]) -> Any:
    data = answer.get("data")
    return data.get("id") if isinstance(data, Mapping) else None


def _write(context: Context, path: str, wire: dict[str, Any]) -> dict[str, Any]:
    return context.transport.write(path, wire, single_object=True)


# -- connection ---------------------------------------------------------------------------


def test_connection(context: Context) -> dict[str, Any]:
    values.closed(context.operation_input, frozenset({"connection_ref"}), "The step input")
    context.transport.read("reference-book/currencies/list", {"rows": 10})
    return {"connected": True, "warnings": []}


# -- clients ------------------------------------------------------------------------------

CLIENT_KEYS = {"code": "code", "vat_code": "vatCode", "email": "email"}
CLIENT_CREATE = {
    "name": "name",
    "short_name": "shortName",
    "location_id": "locationId",
    "is_juridical": "isJuridical",
    "phone_number": "phoneNumber",
    "is_supplier": "isSupplier",
}
FIND_CLIENT_INPUTS = frozenset(CLIENT_KEYS)
FIND_OR_CREATE_CLIENT_INPUTS = frozenset(CLIENT_KEYS) | frozenset(CLIENT_CREATE)


def find_client(context: Context) -> dict[str, Any]:
    values.closed(
        context.operation_input, FIND_CLIENT_INPUTS | {"connection_ref"}, "The step input"
    )
    rules = _keys(context.operation_input, CLIENT_KEYS)
    client = _one(_find(context, "clients/list", rules), "client", _described(rules))
    return {"found": client is not None, "client": client, "warnings": []}


def _described(rules: list[tuple[str, str]]) -> str:
    return " and ".join(f"{f} {v}" for f, v in rules)


def _client_body(
    operation_input: Mapping[str, Any], rules: list[tuple[str, str]]
) -> dict[str, Any]:
    given = {
        CLIENT_CREATE[k]: operation_input[k]
        for k in CLIENT_CREATE
        if operation_input.get(k) is not None
    }
    given.update({field: value for field, value in rules})
    nodes = registry()["clients_create"]["params"]
    return request_body_from(nodes, given)


def request_body_from(nodes: list[Mapping[str, Any]], given: Mapping[str, Any]) -> dict[str, Any]:
    return body(nodes, given)


def find_or_create_client(context: Context) -> dict[str, Any]:
    operation_input = context.operation_input
    values.closed(
        operation_input, FIND_OR_CREATE_CLIENT_INPUTS | {"connection_ref"}, "The step input"
    )
    rules = _keys(operation_input, CLIENT_KEYS)
    wire = _client_body(operation_input, rules)  # checked before anything is asked for
    client = _one(_find(context, "clients/list", rules), "client", _described(rules))
    if client is not None:
        return {"client_id": client.get("id"), "created": False, "client": client, "warnings": []}
    answer = _write(context, "clients/create", wire)
    return {"client_id": _created_id(answer), "created": True, "client": None, "warnings": []}


# -- items --------------------------------------------------------------------------------

ITEM_KEYS = {"code": "code", "barcode": "barcode"}
ITEM_CREATE = {
    "name": "name",
    "attribute_id": "attributeId",
    "measurement_unit_id": "measurementUnitId",
    "group_id": "groupId",
    "price_without_vat": "priceWithoutVat",
    "vat_rate": "vatRate",
    "price_with_vat": "priceWithVat",
}
FIND_ITEM_INPUTS = frozenset(ITEM_KEYS)
FIND_OR_CREATE_ITEM_INPUTS = frozenset(ITEM_KEYS) | frozenset(ITEM_CREATE)


def find_item(context: Context) -> dict[str, Any]:
    values.closed(context.operation_input, FIND_ITEM_INPUTS | {"connection_ref"}, "The step input")
    rules = _keys(context.operation_input, ITEM_KEYS)
    item = _one(_find(context, "reference-book/items/list", rules), "item", _described(rules))
    return {"found": item is not None, "item": item, "warnings": []}


def find_or_create_item(context: Context) -> dict[str, Any]:
    operation_input = context.operation_input
    values.closed(
        operation_input, FIND_OR_CREATE_ITEM_INPUTS | {"connection_ref"}, "The step input"
    )
    rules = _keys(operation_input, ITEM_KEYS)
    given = {
        ITEM_CREATE[k]: operation_input[k]
        for k in ITEM_CREATE
        if operation_input.get(k) is not None
    }
    given.update({field: value for field, value in rules})
    wire = request_body_from(registry()["reference_book_items_create"]["params"], given)
    item = _one(_find(context, "reference-book/items/list", rules), "item", _described(rules))
    if item is not None:
        return {"item_id": item.get("id"), "created": False, "item": item, "warnings": []}
    answer = _write(context, "reference-book/items/create", wire)
    return {"item_id": _created_id(answer), "created": True, "item": None, "warnings": []}


# -- sales ----------------------------------------------------------------------------------

SALE_HEADER = {
    "transaction_id": "transactionId",
    "sale_date": "saleDate",
    "pay_until": "payUntil",
    "warehouse_id": "warehouseId",
    "client_id": "clientId",
    "operation_type_id": "operationTypeId",
    "employee_id": "employeeId",
    "series": "series",
    "number": "number",
    "vat_rate_id": "vatRateId",
    "notes": "notes",
    "order_number_client": "orderNumberClient",
}
SALE_LINE = {
    "item_id": "itemId",
    "quantity": "quantity",
    "price_without_vat": "priceWithoutVat",
    "price_with_vat": "priceWithVat",
    "vat_rate": "vatRate",
    "discount_rate": "discountRate",
    "vat_classification_id": "vatClassificationId",
    "warehouse_id": "warehouseId",
    "postscript_text": "postscriptText",
}
SALES_INVOICE_INPUTS = frozenset(SALE_HEADER) | {"lines"}


def _lines(operation_input: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return values.records(operation_input.get("lines"), "lines", max_items=MAX_LINES)


def sales_invoice_bodies(
    operation_input: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    values.closed(operation_input, SALES_INVOICE_INPUTS | {"connection_ref"}, "The step input")
    transaction = values.required_text(
        operation_input.get("transaction_id"), "transaction_id", max_length=100
    )
    given = {
        SALE_HEADER[k]: operation_input[k]
        for k in SALE_HEADER
        if operation_input.get(k) is not None
    }
    numbered = "series" in given or "number" in given
    if numbered and not ("series" in given and "number" in given):
        raise invalid("Give both the series and the number, or neither to have them generated")
    given["autoGenerateNumberAndSeries"] = not numbered
    header = request_body_from(registry()["warehouse_sales_create"]["params"], given)
    line_nodes = [
        n
        for n in registry()["warehouse_sale_items_create_simple"]["params"]
        if n["name"] != "saleId"
    ]
    lines = []
    for index, line in enumerate(_lines(operation_input), start=1):
        values.closed(line, frozenset(SALE_LINE), f"Line {index}")
        wire_line = {SALE_LINE[k]: v for k, v in line.items() if v is not None}
        lines.append(request_body_from(line_nodes, wire_line))
    return header, lines, transaction


def _partial(created: str, failure: ExtensionError) -> ExtensionError:
    return ExtensionError(
        failure.code,
        f"{created}; then: {failure.message}. Nothing created was deleted: finish or remove it "
        "in Site.pro Accounting before running the step again",
        failure_class=failure.failure_class,
        retryable=False,
        definitely_no_external_effect=False,
        external_effect_status="timeout_unknown",
        http_status=failure.http_status,
    )


def create_sales_invoice(context: Context) -> dict[str, Any]:
    header, lines, transaction = sales_invoice_bodies(context.operation_input)
    existing = _find(context, "warehouse/sales/list", [("transactionId", transaction)])
    if existing:
        ids = ", ".join(str(r.get("id")) for r in existing[:5])
        raise errors.no_effect(
            errors.CONFLICT,
            f"Site.pro Accounting already has a sale with transaction ID {transaction} (id "
            f"{ids}); nothing was created",
        )
    answer = _write(context, "warehouse/sales/create", header)
    sale_id = _created_id(answer)
    if sale_id is None:
        raise _partial(
            "The sale was created but Site.pro Accounting returned no id",
            errors.no_effect(errors.INVALID_RESPONSE, "its lines were not created"),
        )
    line_ids: list[Any] = []
    for index, line in enumerate(lines, start=1):
        try:
            got = _write(context, "warehouse/sale-items/create-simple", {"saleId": sale_id, **line})
        except ExtensionError as exc:
            raise _partial(
                f"Sale {sale_id} and {len(line_ids)} of its {len(lines)} lines were created "
                f"(line ids {line_ids or 'none'}); line {index} failed",
                exc,
            ) from None
        except DeadlineReached:
            raise _partial(
                f"Sale {sale_id} and {len(line_ids)} of its {len(lines)} lines were created; "
                f"the step ran out of time before line {index}",
                errors.no_effect(errors.TIMEOUT, "time ran out"),
            ) from None
        line_ids.append(_created_id(got))
    return {"sale_id": sale_id, "line_ids": line_ids, "transaction_id": transaction, "warnings": []}


FIND_SALE_INPUTS = frozenset({"transaction_id", "series", "number"})


def find_sale(context: Context) -> dict[str, Any]:
    operation_input = context.operation_input
    values.closed(operation_input, FIND_SALE_INPUTS | {"connection_ref"}, "The step input")
    rules = []
    transaction = values.text(
        operation_input.get("transaction_id"), "transaction_id", max_length=100
    )
    series = values.text(operation_input.get("series"), "series", max_length=50)
    number = values.text(operation_input.get("number"), "number", max_length=50)
    if transaction:
        rules.append(("transactionId", transaction))
    if series or number:
        if not (series and number):
            raise invalid("Give both the series and the number")
        rules += [("series", str(series)), ("number", str(number))]
    if not rules:
        raise invalid("Give the transaction ID, or the series and the number")
    sale = _one(_find(context, "warehouse/sales/list", rules), "sale", _described(rules))
    return {"found": sale is not None, "sale": sale, "warnings": []}


# -- purchases -----------------------------------------------------------------------------

PURCHASE_HEADER = {
    "supplier_id": "supplierId",
    "number": "number",
    "series": "series",
    "purchase_date": "purchaseDate",
    "pay_until": "payUntil",
    "warehouse_id": "warehouseId",
    "operation_type_id": "operationTypeId",
    "currency_id": "currencyId",
    "employee_id": "employeeId",
    "vat_rate_id": "vatRateId",
    "vat": "vat",
    "notes": "notes",
}
PURCHASE_LINE = {
    "item_id": "itemId",
    "quantity": "quantity",
    "price_without_vat": "priceWithoutVat",
    "price_with_vat": "priceWithVat",
    "vat_rate": "vatRate",
    "vat_classification_id": "vatClassificationId",
    "warehouse_id": "warehouseId",
    "notes": "notes",
}
PURCHASE_INVOICE_INPUTS = frozenset(PURCHASE_HEADER) | {"lines"}


def purchase_invoice_bodies(
    operation_input: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[tuple[str, str]]]:
    values.closed(operation_input, PURCHASE_INVOICE_INPUTS | {"connection_ref"}, "The step input")
    given = {
        PURCHASE_HEADER[k]: operation_input[k]
        for k in PURCHASE_HEADER
        if operation_input.get(k) is not None
    }
    header = request_body_from(registry()["warehouse_purchases_create"]["params"], given)
    line_nodes = [
        n
        for n in registry()["warehouse_purchase_items_create"]["params"]
        if n["name"] not in {"purchaseId", "position"}
    ]
    lines = []
    for index, line in enumerate(_lines(operation_input), start=1):
        values.closed(line, frozenset(PURCHASE_LINE), f"Line {index}")
        wire_line: dict[str, Any] = {PURCHASE_LINE[k]: v for k, v in line.items() if v is not None}
        if "warehouseId" not in wire_line and "warehouseId" in header:
            wire_line["warehouseId"] = header["warehouseId"]
        # No discount: the discount fields Site.pro Accounting requires are zero and the
        # discounted price is the price.
        wire_line.setdefault("discountRate", 0)
        wire_line.setdefault("discount", 0)
        wire_line.setdefault("discountSum", 0)
        if "priceWithoutVat" in wire_line:
            wire_line.setdefault("priceWithoutVatWithDiscount", wire_line["priceWithoutVat"])
        checked = request_body_from(line_nodes, wire_line)
        lines.append(checked)
    duplicate = [("clientId", str(header.get("supplierId"))), ("number", str(header.get("number")))]
    if header.get("series"):
        duplicate.append(("series", str(header["series"])))
    return header, lines, duplicate


def create_purchase_invoice(context: Context) -> dict[str, Any]:
    header, lines, duplicate = purchase_invoice_bodies(context.operation_input)
    existing = _find(context, "warehouse/purchases/list", duplicate)
    if existing:
        raise errors.no_effect(
            errors.CONFLICT,
            f"Site.pro Accounting already has this supplier's purchase {_described(duplicate)} "
            f"(id {existing[0].get('id')}); nothing was created",
        )
    answer = _write(context, "warehouse/purchases/create", header)
    purchase_id = _created_id(answer)
    if purchase_id is None:
        raise _partial(
            "The purchase was created but Site.pro Accounting returned no id",
            errors.no_effect(errors.INVALID_RESPONSE, "its lines were not created"),
        )
    line_ids: list[Any] = []
    for index, line in enumerate(lines, start=1):
        try:
            got = _write(
                context,
                "warehouse/purchase-items/create",
                {"purchaseId": purchase_id, "position": index, **line},
            )
        except ExtensionError as exc:
            raise _partial(
                f"Purchase {purchase_id} and {len(line_ids)} of its {len(lines)} lines were "
                f"created (line ids {line_ids or 'none'}); line {index} failed",
                exc,
            ) from None
        except DeadlineReached:
            raise _partial(
                f"Purchase {purchase_id} and {len(line_ids)} of its {len(lines)} lines were "
                f"created; the step ran out of time before line {index}",
                errors.no_effect(errors.TIMEOUT, "time ran out"),
            ) from None
        line_ids.append(_created_id(got))
    return {"purchase_id": purchase_id, "line_ids": line_ids, "warnings": []}


# -- payments ------------------------------------------------------------------------------

PAYMENT = {
    "sale_id": "saleId",
    "payment_id": "paymentId",
    "payment_date": "paymentDate",
    "amount": "sum",
    "tax": "tax",
    "currency": "currency",
    "purpose": "purpose",
}
SALE_PAYMENT_INPUTS = frozenset(PAYMENT)


def sale_payment_body(operation_input: Mapping[str, Any]) -> dict[str, Any]:
    values.closed(operation_input, SALE_PAYMENT_INPUTS | {"connection_ref"}, "The step input")
    given = {PAYMENT[k]: operation_input[k] for k in PAYMENT if operation_input.get(k) is not None}
    return request_body_from(registry()["bank_sale_invoice_payment"]["params"], given)


def record_sale_payment(context: Context) -> dict[str, Any]:
    wire = sale_payment_body(context.operation_input)
    existing = _find(context, "bank/transactions/list", [("number", str(wire["paymentId"]))])
    if existing:
        raise errors.no_effect(
            errors.CONFLICT,
            f"Site.pro Accounting already has a bank transaction numbered {wire['paymentId']} "
            f"(id {existing[0].get('id')}); the payment was not recorded again",
        )
    answer = _write(context, "bank/sale-invoice/payment", wire)
    data = answer.get("data")
    transaction = data.get("transactionId") if isinstance(data, Mapping) else None
    return {
        "transaction_id": None if transaction is None else str(transaction),
        "payment_id": wire["paymentId"],
        "warnings": [],
    }


# -- reports -------------------------------------------------------------------------------

GET_REPORT_INPUTS = frozenset({"report", "parameters"})


def report_operation(operation_input: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    values.closed(operation_input, GET_REPORT_INPUTS | {"connection_ref"}, "The step input")
    report = values.required_text(operation_input.get("report"), "report", max_length=120)
    entry = registry().get(report)
    if entry is None or entry["kind"] != "report":
        raise invalid("report must be the id of a Generate … report step")
    parameters = operation_input.get("parameters") or {}
    if not isinstance(parameters, Mapping):
        raise invalid("parameters must be an object")
    return report, request_body(report, parameters)


def get_report(
    context: Context,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    report, wire = report_operation(context.operation_input)
    transport = context.transport
    answer = transport.read(registry()[report]["path"], wire)
    task = answer.get("taskId")
    if task is None:
        raise errors.no_effect(
            errors.INVALID_RESPONSE, "Site.pro Accounting returned no task ID for the report"
        )
    while True:
        try:
            got = transport.read_file("reports/get", {"taskId": task})
        except ExtensionError as exc:
            if exc.code == errors.AUTHENTICATION_FAILED:
                raise
            # Not ready yet: asked again while there is time.
            if transport.remaining() < REPORT_POLL_SECONDS + MIN_CALL_WINDOW_SECONDS:
                return {
                    "ready": False,
                    "task_id": task,
                    "file": None,
                    "file_name": None,
                    "mime_type": None,
                    "size_bytes": None,
                    "warnings": [
                        f"The report was not ready in time ({exc.message}); get it "
                        "later with Get a generated report file and this task ID"
                    ],
                }
            sleep(REPORT_POLL_SECONDS)
            continue
        if got.file is None:
            if transport.remaining() < REPORT_POLL_SECONDS + MIN_CALL_WINDOW_SECONDS:
                return {
                    "ready": False,
                    "task_id": task,
                    "file": None,
                    "file_name": None,
                    "mime_type": None,
                    "size_bytes": None,
                    "warnings": [
                        "The report was not ready in time; get it later with Get a "
                        "generated report file and this task ID"
                    ],
                }
            sleep(REPORT_POLL_SECONDS)
            continue
        handle = files.save(
            context,
            got.file,
            binding_key=files.DOWNLOAD_BINDING,
            content_type=files.DOWNLOAD_CONTENT_TYPE,
            what="The report",
        )
        return {
            "ready": True,
            "task_id": task,
            "file": handle,
            "file_name": got.file_name or None,
            "mime_type": got.content_type or None,
            "size_bytes": len(got.file),
            "warnings": [],
        }


COMPOSITES: dict[str, Callable[[Context], dict[str, Any]]] = {
    "test_connection": test_connection,
    "find_client": find_client,
    "find_or_create_client": find_or_create_client,
    "find_item": find_item,
    "find_or_create_item": find_or_create_item,
    "create_sales_invoice": create_sales_invoice,
    "find_sale": find_sale,
    "create_purchase_invoice": create_purchase_invoice,
    "record_sale_payment": record_sale_payment,
    "get_report": get_report,
}
COMPOSITE_WRITES = frozenset(
    {
        "find_or_create_client",
        "find_or_create_item",
        "create_sales_invoice",
        "create_purchase_invoice",
        "record_sale_payment",
    }
)


def client_bodies(operation_input: Mapping[str, Any]) -> dict[str, Any]:
    values.closed(
        operation_input, FIND_OR_CREATE_CLIENT_INPUTS | {"connection_ref"}, "The step input"
    )
    return _client_body(operation_input, _keys(operation_input, CLIENT_KEYS))


def item_bodies(operation_input: Mapping[str, Any]) -> dict[str, Any]:
    values.closed(
        operation_input, FIND_OR_CREATE_ITEM_INPUTS | {"connection_ref"}, "The step input"
    )
    given = {
        ITEM_CREATE[k]: operation_input[k]
        for k in ITEM_CREATE
        if operation_input.get(k) is not None
    }
    given.update(dict(_keys(operation_input, ITEM_KEYS)))
    return request_body_from(registry()["reference_book_items_create"]["params"], given)


#: Checks an everyday write's inputs without calling Site.pro Accounting (test runs).
VALIDATORS: dict[str, Callable[[Mapping[str, Any]], Any]] = {
    "find_or_create_client": client_bodies,
    "find_or_create_item": item_bodies,
    "create_sales_invoice": sales_invoice_bodies,
    "create_purchase_invoice": purchase_invoice_bodies,
    "record_sale_payment": sale_payment_body,
}
INPUTS: dict[str, frozenset[str]] = {
    "test_connection": frozenset(),
    "find_client": FIND_CLIENT_INPUTS,
    "find_or_create_client": FIND_OR_CREATE_CLIENT_INPUTS,
    "find_item": FIND_ITEM_INPUTS,
    "find_or_create_item": FIND_OR_CREATE_ITEM_INPUTS,
    "create_sales_invoice": SALES_INVOICE_INPUTS,
    "find_sale": FIND_SALE_INPUTS,
    "create_purchase_invoice": PURCHASE_INVOICE_INPUTS,
    "record_sale_payment": SALE_PAYMENT_INPUTS,
    "get_report": GET_REPORT_INPUTS,
}

__all__ = ["COMPOSITES", "COMPOSITE_WRITES", "INPUTS", "VALIDATORS"]
