# LedgerLite

LedgerLite is a wallet backend built with Django, PostgreSQL, and FastAPI. It supports deposits, transfers, credit purchases, and transaction history.

## Tech Stack

- Python 3.12
- Django
- Django REST Framework
- FastAPI (payment provider mock)
- PostgreSQL 16
- Docker Compose
- pytest and Ruff

## Quick Start

1. Create the environment file:

   cp .env.example .env

2. Set local secrets in `.env`.

3. Start the services:

   docker compose up -d --build

The services are available at:

- Wallet API: http://localhost:8000
- Provider Mock: http://localhost:8001
- Provider Swagger UI: http://localhost:8001/docs

## Wallet API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /v1/accounts/me | Account balance and credits |
| POST | /v1/deposits | Create a deposit invoice |
| POST | /v1/transfers | Transfer funds between accounts |
| POST | /v1/purchases | Purchase credits |
| GET | /v1/transactions | Paginated transaction history |
| POST | /v1/webhooks/provider | Process signed payment webhooks |

Protected wallet endpoints require the `X-API-Key` header.

Transfers additionally require an `Idempotency-Key` header.

## Provider Mock API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /invoices | Create an invoice |
| GET | /invoices/{invoice_id} | Retrieve an invoice |
| POST | /invoices/{invoice_id}/simulate | Simulate payment |

Provider endpoints require `Authorization: Bearer <PROVIDER_API_KEY>`.

Supported simulation statuses: `paid`, `partially_paid`, `expired`.

The mock can deliver duplicate signed webhooks for idempotency testing.

## Business Rules

### Deposits

A 1.5% processing fee is deducted from the paid amount. The credited balance is rounded to two decimal places using ROUND_HALF_UP.

Webhooks use HMAC-SHA256 signatures with timestamp validation. Duplicate deliveries must not credit the wallet twice.

### Transfers

Transfers use database transactions and row-level locking to prevent overdrafts.

An idempotency key prevents duplicate transfers. Reusing a key with different transfer data returns HTTP 409.

### Credit Purchases

One credit costs $0.10 before discounts.

- Fewer than 500 credits: no discount
- 500–999 credits: 5% discount
- 1000 or more credits: 12.5% discount

Amounts are rounded using ROUND_HALF_UP.

## Tests

Run all tests:

    docker compose run --rm wallet-service pytest -q

Run Ruff:

    docker compose run --rm wallet-service ruff check .

## CI

GitHub Actions runs Ruff and pytest with PostgreSQL.

## Notes

The provider mock stores invoices in memory, so its data is reset when the service restarts.

Secrets are configured through `.env`, which is excluded from Git.
