from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from wallet.models import Transfer, Wallet
from wallet.services import execute_transfer


@pytest.fixture
def accounts(db):
    User = get_user_model()
    alice = User.objects.create_user(
        username="alice_test", password="testpass"
    )
    bob = User.objects.create_user(
        username="bob_test", password="testpass"
    )
    sender = Wallet.objects.create(
        user=alice, balance=Decimal("100.00")
    )
    recipient = Wallet.objects.create(
        user=bob, balance=Decimal("0.00")
    )
    return alice, sender, recipient


def test_successful_transfer(accounts):
    alice, sender, recipient = accounts

    transfer, created = execute_transfer(
        alice, recipient.id, Decimal("25.00"), "key-1"
    )

    sender.refresh_from_db()
    recipient.refresh_from_db()

    assert created is True
    assert transfer.amount == Decimal("25.00")
    assert sender.balance == Decimal("75.00")
    assert recipient.balance == Decimal("25.00")


def test_idempotent_transfer(accounts):
    alice, sender, recipient = accounts

    first, created_first = execute_transfer(
        alice, recipient.id, Decimal("25.00"), "key-1"
    )
    second, created_second = execute_transfer(
        alice, recipient.id, Decimal("25.00"), "key-1"
    )

    sender.refresh_from_db()
    recipient.refresh_from_db()

    assert created_first is True
    assert created_second is False
    assert first.id == second.id
    assert Transfer.objects.count() == 1
    assert sender.balance == Decimal("75.00")
    assert recipient.balance == Decimal("25.00")


def test_idempotency_conflict(accounts):
    alice, _, recipient = accounts

    execute_transfer(
        alice, recipient.id, Decimal("25.00"), "key-1"
    )

    with pytest.raises(ValueError, match="idempotency_conflict"):
        execute_transfer(
            alice, recipient.id, Decimal("30.00"), "key-1"
        )


def test_insufficient_funds(accounts):
    alice, sender, recipient = accounts

    with pytest.raises(ValueError, match="insufficient_funds"):
        execute_transfer(
            alice, recipient.id, Decimal("150.00"), "key-2"
        )

    sender.refresh_from_db()
    recipient.refresh_from_db()

    assert sender.balance == Decimal("100.00")
    assert recipient.balance == Decimal("0.00")
    assert Transfer.objects.count() == 0
