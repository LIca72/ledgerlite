import hashlib
import json
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from wallet.models import APIKey, Purchase, Wallet


@pytest.fixture
def buyer(db):
    user = get_user_model().objects.create_user(
        username="buyer_test", password="testpass"
    )
    key = "purchase-test-key"
    APIKey.objects.create(
        user=user,
        key_hash=hashlib.sha256(key.encode()).hexdigest(),
    )
    wallet = Wallet.objects.create(
        user=user, balance=Decimal("200.00")
    )
    return Client(), key, wallet


@pytest.mark.parametrize(
    "credits, expected_amount",
    [
        (100, "10.00"),
        (333, "33.30"),
        (500, "47.50"),
        (507, "48.17"),
        (1000, "87.50"),
        (1005, "87.94"),
    ],
)
def test_purchase_prices(buyer, credits, expected_amount):
    client, key, wallet = buyer

    response = client.post(
        "/v1/purchases",
        data=json.dumps({"credits": credits}),
        content_type="application/json",
        HTTP_X_API_KEY=key,
    )

    assert response.status_code == 201, response.content
    assert response.json()["amount"] == expected_amount

    wallet.refresh_from_db()
    assert wallet.credits == credits
    assert wallet.balance == (
        Decimal("200.00") - Decimal(expected_amount)
    )
    assert Purchase.objects.count() == 1


@pytest.mark.parametrize(
    "credits",
    [0, -1, 1.5, "100", True, None],
)
def test_purchase_invalid_credits(buyer, credits):
    client, key, wallet = buyer

    response = client.post(
        "/v1/purchases",
        data=json.dumps({"credits": credits}),
        content_type="application/json",
        HTTP_X_API_KEY=key,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_credits"

    wallet.refresh_from_db()
    assert wallet.balance == Decimal("200.00")
    assert wallet.credits == 0
    assert Purchase.objects.count() == 0
