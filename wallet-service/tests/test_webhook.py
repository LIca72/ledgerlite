import hashlib
import hmac
import time
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from wallet.models import Deposit, Wallet
from wallet.services import (
    process_deposit_webhook,
    verify_webhook_signature,
)


def test_valid_signature():
    timestamp = str(int(time.time()))
    body = b'{"status":"paid"}'
    secret = "test-secret"
    message = timestamp.encode() + b"." + body
    signature = "sha256=" + hmac.new(
        secret.encode(), message, hashlib.sha256
    ).hexdigest()

    assert verify_webhook_signature(
        body, timestamp, signature, secret
    )


def test_invalid_signature():
    assert not verify_webhook_signature(
        b"body", str(int(time.time())),
        "sha256=invalid", "test-secret"
    )


def test_expired_signature():
    assert not verify_webhook_signature(
        b"body", str(int(time.time()) - 600),
        "sha256=invalid", "test-secret"
    )


@pytest.fixture
def pending_deposit(db):
    user = get_user_model().objects.create_user(
        username="webhook_test", password="testpass"
    )
    wallet = Wallet.objects.create(
        user=user, balance=Decimal("0.00")
    )
    deposit = Deposit.objects.create(
        wallet=wallet,
        amount=Decimal("10.00"),
        invoice_id="test-invoice-1",
    )
    return wallet, deposit


def test_paid_webhook(pending_deposit):
    wallet, deposit = pending_deposit

    assert process_deposit_webhook(
        deposit.invoice_id, "paid", "10.00"
    )

    wallet.refresh_from_db()
    deposit.refresh_from_db()

    assert wallet.balance == Decimal("9.85")
    assert deposit.status == "paid"


def test_duplicate_webhook(pending_deposit):
    wallet, deposit = pending_deposit

    process_deposit_webhook(
        deposit.invoice_id, "paid", "10.00"
    )
    result = process_deposit_webhook(
        deposit.invoice_id, "paid", "10.00"
    )

    wallet.refresh_from_db()

    assert result is False
    assert wallet.balance == Decimal("9.85")


def test_expired_payment(pending_deposit):
    wallet, deposit = pending_deposit

    assert process_deposit_webhook(
        deposit.invoice_id, "expired", "0.00"
    )

    wallet.refresh_from_db()
    deposit.refresh_from_db()

    assert wallet.balance == Decimal("0.00")
    assert deposit.status == "expired"
