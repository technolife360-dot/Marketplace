"""Small server-side SEAGM Open API client.

Supplier credentials must only be provided through deployment secrets or the
private local .env file. This module deliberately exposes no order creation
operation yet: Top Up sales must stay closed until a real payment adapter and
the SEAGM product/region mapping have been configured.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SANDBOX_URL = "https://openapi.seagm.io"
PRODUCTION_URL = "https://openapi.seagm.com"


class SupplierError(RuntimeError):
    """A sanitized supplier API/configuration error."""


def configuration():
    uid = os.environ.get("SEAGM_UID", "").strip()
    secret = os.environ.get("SEAGM_SECRET_KEY", "").strip()
    environment = os.environ.get("SEAGM_API_ENV", "sandbox").strip().lower()
    if environment not in ("sandbox", "production"):
        environment = "sandbox"
    return {
        "configured": bool(uid and secret),
        "uid": uid,
        "secret": secret,
        "environment": environment,
        "base_url": SANDBOX_URL if environment == "sandbox" else PRODUCTION_URL,
    }


def _signed_parameters(uid: str, secret: str, parameters: dict[str, object]) -> tuple[dict[str, str], str]:
    values = {key: str(value) for key, value in parameters.items() if value is not None}
    values["uid"] = uid
    values["timestamp"] = str(int(time.time()))
    # SEAGM signs the complete parameter string, sorted by parameter name.
    unsigned = urlencode(sorted(values.items()))
    signature = hmac.new(secret.encode(), unsigned.encode(), hashlib.sha256).hexdigest()
    values["signature"] = signature
    return values, unsigned


def request(path: str, parameters: dict[str, object] | None = None, *, method="GET", timeout=12):
    config = configuration()
    if not config["configured"]:
        raise SupplierError("SEAGM API kalitlari serverda sozlanmagan.")
    method = method.upper()
    parameters = parameters or {}
    signed, _ = _signed_parameters(config["uid"], config["secret"], parameters)
    base_url = config["base_url"]
    if method == "GET":
        url = base_url + path + "?" + urlencode(sorted(signed.items()))
        body = None
    elif method == "POST":
        auth = {key: signed[key] for key in ("uid", "timestamp", "signature")}
        payload = {key: str(value) for key, value in parameters.items() if value is not None}
        url = base_url + path + "?" + urlencode(sorted(auth.items()))
        body = urlencode(payload).encode()
    else:
        raise SupplierError("SEAGM so‘rov usuli qo‘llab-quvvatlanmaydi.")
    req = Request(url, data=body, headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read(1_000_001)
    except HTTPError as error:
        # Do not relay arbitrary upstream response bodies or credentials.
        raise SupplierError(f"SEAGM API HTTP {error.code} javobini qaytardi.") from None
    except (URLError, TimeoutError, OSError):
        raise SupplierError("SEAGM API bilan bog‘lanib bo‘lmadi. Tarmoq va sandbox holatini tekshiring.") from None
    if len(raw) > 1_000_000:
        raise SupplierError("SEAGM javobi kutilgan hajmdan katta.")
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SupplierError("SEAGM API JSON formatida javob bermadi.") from None
    if not isinstance(result, dict):
        raise SupplierError("SEAGM API javobining formati noto‘g‘ri.")
    if result.get("code") not in (None, 200, 2000, 2010):
        code = str(result.get("code", ""))[:20]
        error_info = result.get("error_info") if isinstance(result.get("error_info"), dict) else {}
        message = str(error_info.get("info_message") or result.get("msg") or result.get("message") or "")[:180]
        raise SupplierError(f"SEAGM API xatosi {code}: {message}".strip())
    return result


def account_status():
    config = configuration()
    if not config["configured"]:
        return {"configured": False, "environment": config["environment"], "connected": False}
    result = request("/v1/me")
    account = result.get("data") if isinstance(result.get("data"), dict) else {}
    balance = account.get("balance")
    credits = account.get("credits")
    return {
        "configured": True,
        "environment": config["environment"],
        "connected": True,
        "account_id": str(account.get("id") or config["uid"]),
        "username": str(account.get("username") or "")[:100],
        "currency": str(account.get("currency") or "")[:12],
        "balance": str(balance) if balance is not None else None,
        "credits": str(credits) if credits is not None else None,
    }


def catalog_categories():
    """Fetch supplier direct top-up categories for admin-only inspection."""
    result = request("/v1/recharge-categories")
    categories = result.get("data")
    if not isinstance(categories, list):
        raise SupplierError("SEAGM katalog javobida kategoriya ro‘yxati topilmadi.")
    return [
        {"id": row.get("id"), "name": str(row.get("name") or "")[:160],
         "code": str(row.get("code") or "")[:120], "auto_delivery": bool(row.get("auto_delivery"))}
        for row in categories if isinstance(row, dict)
    ]


def catalog_types(category_id: int):
    """Fetch purchasable type IDs and required player fields for a category."""
    result = request(f"/v1/recharge-categories/{category_id}/recharge-types")
    products = result.get("data")
    if not isinstance(products, list):
        raise SupplierError("SEAGM javobida paketlar ro‘yxati topilmadi.")
    output = []
    for row in products[:500]:
        if not isinstance(row, dict):
            continue
        fields = row.get("fields") if isinstance(row.get("fields"), list) else []
        output.append({
            "id": str(row.get("id") or ""),
            "name": str(row.get("name") or "")[:160],
            "category_id": str(row.get("category_id") or category_id),
            "par_value": str(row.get("par_value") or "")[:40],
            "par_value_currency": str(row.get("par_value_currency") or "")[:12],
            "unit_price": str(row.get("unit_price") or "")[:40],
            "currency": str(row.get("currency") or "")[:12],
            "account_check": bool(row.get("account_check")),
            "fields": [
                {"name": str(field.get("name") or "")[:100],
                 "label": str(field.get("label") or "")[:100],
                 "type": str(field.get("type") or "input")[:30],
                 "required": True}
                for field in fields if isinstance(field, dict)
            ],
        })
    return output
