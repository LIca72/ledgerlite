from django.conf import settings
from django.db import models


class Wallet(models.Model):
    credits = models.PositiveIntegerField(default=0)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallet",
    )
    balance = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
    )
    currency = models.CharField(
        max_length=3,
        default="USD",
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Wallet of {self.user_id}"
    
class Deposit(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        PARTIALLY_PAID = "partially_paid", "Partially paid"
        EXPIRED = "expired", "Expired"

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name="deposits",
    )
    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
    )
    paid_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
    )
    credited_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
    )
    invoice_id = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)


class APIKey(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    key_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Transfer(models.Model):
    sender = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name="outgoing_transfers",
    )
    recipient = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name="incoming_transfers",
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    idempotency_key = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sender", "idempotency_key"],
                name="unique_sender_idempotency_key",
            ),
        ]


class Purchase(models.Model):
    wallet = models.ForeignKey(
        Wallet, on_delete=models.PROTECT, related_name="purchases"
    )
    credits = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
