from rest_framework import serializers


class PurchaseSerializer(serializers.Serializer):
    credits = serializers.IntegerField(min_value=1)

    def validate_credits(self, value):
        if type(self.initial_data.get("credits")) is not int:
            raise serializers.ValidationError(
                "Credits must be a positive integer"
            )
        return value


class TransferSerializer(serializers.Serializer):
    amount = serializers.CharField()
    to_account_id = serializers.IntegerField(min_value=1)

    def validate_amount(self, value):
        from decimal import Decimal, InvalidOperation

        try:
            amount = Decimal(value)
        except (InvalidOperation, TypeError):
            raise serializers.ValidationError("Invalid amount")

        if (
            not amount.is_finite()
            or amount < Decimal("0.01")
            or amount.as_tuple().exponent < -2
        ):
            raise serializers.ValidationError("Invalid amount")

        return amount
