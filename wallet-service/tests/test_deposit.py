from decimal import Decimal

import pytest

from wallet.services import calculate_deposit_credit


@pytest.mark.parametrize(
    "amount, expected",
    [
        ("10.00", "9.85"),
        ("0.99", "0.98"),
        ("33.33", "32.83"),
        ("100.00", "98.50"),
    ],
)
def test_deposit_fee(amount, expected):
    result = calculate_deposit_credit(Decimal(amount))
    assert result == Decimal(expected)
