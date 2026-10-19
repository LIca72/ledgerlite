import hashlib
import hmac
import json
import os
import time
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="LedgerLite Provider Mock")

API_KEY = os.environ.get("PROVIDER_API_KEY", "local-provider-key")
WEBHOOK_SECRET = os.environ.get(
    "PROVIDER_WEBHOOK_SECRET", "local-webhook-secret-change-me"
)

invoices = {}


class InvoiceRequest(BaseModel):
    amount: str
    currency: str
    external_id: str
    callback_url: str


class SimulateRequest(BaseModel):
    status: str
    paid_amount: str = "0.00"
    deliver_webhook: bool = True
    duplicate: bool = False


def authorize(authorization):
    if not hmac.compare_digest(authorization or "", f"Bearer {API_KEY}"):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/invoices", status_code=201)
def create_invoice(
    data: InvoiceRequest,
    authorization: str | None = Header(default=None),
):
    authorize(authorization)

    try:
        amount = Decimal(data.amount)
        if (
            not amount.is_finite()
            or amount <= 0
            or amount.as_tuple().exponent < -2
            or data.currency != "USD"
        ):
            raise ValueError()
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=422, detail="Invalid amount")

    invoice_id = "inv_" + uuid.uuid4().hex

    invoices[invoice_id] = {
        "invoice_id": invoice_id,
        "external_id": data.external_id,
        "amount": data.amount,
        "currency": data.currency,
        "callback_url": data.callback_url,
        "status": "pending",
        "paid_amount": "0.00",
    }

    return {
        "invoice_id": invoice_id,
        "status": "pending",
        "pay_url": f"http://localhost:8001/invoices/{invoice_id}",
    }


@app.get("/invoices/{invoice_id}")
def get_invoice(
    invoice_id: str,
    authorization: str | None = Header(default=None),
):
    authorize(authorization)

    if invoice_id not in invoices:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return invoices[invoice_id]


def send_webhook(callback_url, payload):
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))

    signature = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(),
        timestamp.encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()

    request = urllib.request.Request(
        callback_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Timestamp": timestamp,
            "X-Signature": signature,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except (urllib.error.URLError, TimeoutError) as exc:
        return str(exc)


@app.post("/invoices/{invoice_id}/simulate")
def simulate_payment(
    invoice_id: str,
    data: SimulateRequest,
    authorization: str | None = Header(default=None),
):
    authorize(authorization)

    invoice = invoices.get(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice["status"] != "pending":
        raise HTTPException(status_code=409, detail="Invoice already finalized")

    if data.status not in ("paid", "partially_paid", "expired"):
        raise HTTPException(status_code=422, detail="Invalid status")

    try:
        paid = Decimal(data.paid_amount)
        expected = Decimal(invoice["amount"])

        if (
            not paid.is_finite()
            or paid < 0
            or paid.as_tuple().exponent < -2
            or paid > expected
        ):
            raise ValueError()

        if data.status == "paid" and paid != expected:
            raise ValueError()
        if data.status == "partially_paid" and not 0 < paid < expected:
            raise ValueError()
        if data.status == "expired" and paid != 0:
            raise ValueError()

    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=422, detail="Invalid paid amount")

    invoice["status"] = data.status
    invoice["paid_amount"] = f"{paid:.2f}"

    webhook_results = []

    if data.deliver_webhook:
        payload = {
            "event_id": "evt_" + uuid.uuid4().hex,
            "invoice_id": invoice_id,
            "status": data.status,
            "paid_amount": invoice["paid_amount"],
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }

        webhook_results.append(
            send_webhook(invoice["callback_url"], payload)
        )

        if data.duplicate:
            webhook_results.append(
                send_webhook(invoice["callback_url"], payload)
            )

    return {
        "invoice_id": invoice_id,
        "status": invoice["status"],
        "paid_amount": invoice["paid_amount"],
        "webhook_results": webhook_results,
    }
