from decimal import Decimal, ROUND_HALF_UP


def calculate_deposit_credit(paid_amount: Decimal) -> Decimal:
    fee = (paid_amount * Decimal("0.015")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    return paid_amount - fee


def verify_webhook_signature(
    raw_body: bytes,
    timestamp: str,
    signature: str,
    secret: str,
) -> bool:
    import hashlib
    import hmac
    import time

    try:
        webhook_time = int(timestamp)
    except (TypeError, ValueError):
        return False

    if abs(time.time() - webhook_time) > 300:
        return False

    message = timestamp.encode() + b"." + raw_body
    expected = "sha256=" + hmac.new(
        secret.encode(),
        message,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


def process_deposit_webhook(invoice_id, status, paid_amount):
    from django.db import transaction
    from django.db.models import F
    from wallet.models import Deposit, Wallet

    if status not in ("paid", "partially_paid", "expired"):
        raise ValueError("Invalid payment status")

    with transaction.atomic():
        deposit = Deposit.objects.select_for_update().get(
            invoice_id=invoice_id
        )

        if deposit.status != Deposit.Status.PENDING:
            return False

        if status == "expired":
            deposit.status = Deposit.Status.EXPIRED
            deposit.save(update_fields=["status"])
            return True

        paid_amount = Decimal(str(paid_amount))

        if not paid_amount.is_finite() or paid_amount <= 0:
            raise ValueError("Invalid paid amount")

        credited = calculate_deposit_credit(paid_amount)

        Wallet.objects.filter(pk=deposit.wallet_id).update(
            balance=F("balance") + credited
        )

        deposit.paid_amount = paid_amount
        deposit.credited_amount = credited
        deposit.status = status
        deposit.save(
            update_fields=[
                "paid_amount",
                "credited_amount",
                "status",
            ]
        )

        return True


def create_provider_invoice(deposit):
    import json
    import urllib.error
    import urllib.request

    from django.conf import settings

    payload = {
        "amount": str(deposit.amount),
        "currency": "USD",
        "external_id": str(deposit.id),
        "callback_url": (
            f"{settings.WALLET_BASE_URL}/v1/webhooks/provider"
        ),
    }

    request = urllib.request.Request(
        url=f"{settings.PROVIDER_BASE_URL}/invoices",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.PROVIDER_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            result = json.load(response)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Payment provider unavailable") from exc

    if not isinstance(result, dict):
        raise RuntimeError("Invalid provider response")

    invoice_id = result.get("invoice_id")
    pay_url = result.get("pay_url")

    if not isinstance(invoice_id, str) or not invoice_id:
        raise RuntimeError("Missing invoice_id")
    if not isinstance(pay_url, str) or not pay_url:
        raise RuntimeError("Missing pay_url")

    return invoice_id, pay_url


def execute_transfer(sender, recipient_id, amount, idempotency_key):
    import hashlib
    import json

    from django.db import transaction
    from django.db.models import F

    from .models import Transfer, Wallet

    request_hash = hashlib.sha256(
        json.dumps(
            {"to_account_id": str(recipient_id), "amount": str(amount)},
            sort_keys=True,
        ).encode()
    ).hexdigest()

    with transaction.atomic():
        sender_wallet = Wallet.objects.get(user=sender)

        # Serialize transfers for the same sender.
        sender_wallet = Wallet.objects.select_for_update().get(
            pk=sender_wallet.pk
        )

        existing = Transfer.objects.filter(
            sender=sender_wallet,
            idempotency_key=idempotency_key,
        ).first()

        if existing:
            if existing.request_hash != request_hash:
                raise ValueError("idempotency_conflict")
            return existing, False

        recipient = Wallet.objects.get(pk=recipient_id)

        if sender_wallet.pk == recipient.pk:
            raise ValueError("self_transfer")

        updated = Wallet.objects.filter(
            pk=sender_wallet.pk,
            balance__gte=amount,
        ).update(balance=F("balance") - amount)

        if not updated:
            raise ValueError("insufficient_funds")

        Wallet.objects.filter(pk=recipient.pk).update(
            balance=F("balance") + amount
        )

        transfer = Transfer.objects.create(
            sender=sender_wallet,
            recipient=recipient,
            amount=amount,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )

        return transfer, True


def calculate_purchase_amount(credits: int) -> Decimal:
    discount = Decimal("0")

    if credits >= 1000:
        discount = Decimal("0.125")
    elif credits >= 500:
        discount = Decimal("0.05")

    return (
        Decimal(credits) * Decimal("0.10") * (Decimal("1") - discount)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def execute_purchase(user, credits: int):
    from django.db import transaction
    from django.db.models import F

    from .models import Purchase, Wallet

    amount = calculate_purchase_amount(credits)

    with transaction.atomic():
        wallet, _ = Wallet.objects.get_or_create(user=user)

        updated = Wallet.objects.filter(
            pk=wallet.pk,
            balance__gte=amount,
        ).update(
            balance=F("balance") - amount,
            credits=F("credits") + credits,
        )

        if not updated:
            raise ValueError("insufficient_funds")

        return Purchase.objects.create(
            wallet=wallet,
            credits=credits,
            amount=amount,
        )
