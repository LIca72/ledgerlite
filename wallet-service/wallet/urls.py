from django.urls import path
from .views import create_transfer, transaction_history, create_purchase, account_me, provider_webhook, create_deposit

urlpatterns = [
    path("v1/transfers", create_transfer, name="create-transfer"),
    path("v1/transactions", transaction_history, name="transaction-history"),
    path("v1/purchases", create_purchase, name="create-purchase"),
    path("v1/accounts/me", account_me, name="account-me"),
    path("v1/webhooks/provider", provider_webhook, name="provider-webhook"),
    path("v1/deposits", create_deposit, name="create-deposit"),
]
