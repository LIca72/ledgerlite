from .responses import error_response
from .auth import require_api_key
from .models import Wallet
import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import Deposit
from .services import (
    process_deposit_webhook,
    verify_webhook_signature,
)


@csrf_exempt
def provider_webhook(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": {"code": "method_not_allowed", "message": "POST required"}},
            status=405,
        )

    timestamp = request.headers.get("X-Timestamp", "")
    signature = request.headers.get("X-Signature", "")

    if not verify_webhook_signature(
        request.body,
        timestamp,
        signature,
        settings.PROVIDER_WEBHOOK_SECRET,
    ):
        return JsonResponse(
            {"error": {"code": "invalid_signature", "message": "Invalid webhook signature"}},
            status=401,
        )

    try:
        data = json.loads(request.body)
        event_id = data["event_id"]
        invoice_id = data["invoice_id"]
        status = data["status"]
        paid_amount = data["paid_amount"]

        if not isinstance(event_id, str) or not event_id:
            raise ValueError("Invalid event_id")
        if not isinstance(invoice_id, str) or not invoice_id:
            raise ValueError("Invalid invoice_id")
        if not isinstance(paid_amount, str):
            raise ValueError("paid_amount must be a string")

        amount = Decimal(paid_amount)
        if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
            raise ValueError("Invalid paid_amount")

        if status not in Deposit.Status.values:
            raise ValueError("Invalid status")

    except (ValueError, KeyError, TypeError, InvalidOperation, json.JSONDecodeError):
        return JsonResponse(
            {"error": {"code": "invalid_payload", "message": "Invalid webhook payload"}},
            status=422,
        )

    try:
        processed = process_deposit_webhook(invoice_id, status, amount)
    except Deposit.DoesNotExist:
        return JsonResponse(
            {"error": {"code": "not_found", "message": "Deposit not found"}},
            status=404,
        )
    except ValueError:
        return JsonResponse(
            {"error": {"code": "invalid_payment", "message": "Invalid payment data"}},
            status=422,
        )

    return JsonResponse({"ok": True, "processed": processed})


@csrf_exempt
@require_api_key("POST")
def create_deposit(request):
    from .models import Wallet
    from .services import create_provider_invoice

    try:
        data = json.loads(request.body)
        raw_amount = data["amount"]

        if not isinstance(raw_amount, str):
            raise ValueError("Amount must be a string")

        amount = Decimal(raw_amount)

        if (
            not amount.is_finite()
            or amount < Decimal("0.01")
            or amount.as_tuple().exponent < -2
        ):
            raise ValueError("Invalid amount")

    except (ValueError, KeyError, TypeError, InvalidOperation, json.JSONDecodeError):
        return error_response('invalid_amount', 'Invalid deposit amount', 422)

    wallet, _ = Wallet.objects.get_or_create(user=request.api_user)
    deposit = Deposit.objects.create(wallet=wallet, amount=amount)

    try:
        invoice_id, pay_url = create_provider_invoice(deposit)
    except RuntimeError:
        return error_response('provider_unavailable', 'Payment provider unavailable', 503)

    deposit.invoice_id = invoice_id
    deposit.save(update_fields=["invoice_id"])

    return JsonResponse(
        {
            "deposit_id": deposit.id,
            "invoice_id": invoice_id,
            "status": deposit.status,
            "amount": str(deposit.amount),
            "pay_url": pay_url,
        },
        status=201,
    )


@csrf_exempt
@require_api_key("POST")
def create_transfer(request):
    from .services import execute_transfer

    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    if not idempotency_key:
        return error_response('missing_idempotency_key', 'Idempotency-Key required', 400)

    from .serializers import TransferSerializer

    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        data = None

    serializer = TransferSerializer(data=data)
    if not serializer.is_valid():
        return error_response('invalid_payload', 'Invalid transfer data', 422)

    amount = serializer.validated_data["amount"]
    recipient_id = serializer.validated_data["to_account_id"]

    try:
        transfer, created = execute_transfer(
            request.api_user, int(recipient_id), amount, idempotency_key
        )
    except Wallet.DoesNotExist:
        return error_response('account_not_found', 'Account not found', 404)
    except ValueError as exc:
        code = str(exc)
        status_code = 409 if code in ("idempotency_conflict", "insufficient_funds") else 422
        return error_response(code, code.replace('_', ' '), status_code)

    return JsonResponse(
        {
            "transfer_id": transfer.id,
            "to_account_id": transfer.recipient_id,
            "amount": str(transfer.amount),
            "status": "completed",
        },
        status=201,
    )


@csrf_exempt
@require_api_key("GET")
def account_me(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.api_user)

    return JsonResponse({
        "account_id": wallet.id,
        "currency": "USD",
        "balance": f"{wallet.balance:.2f}",
        "credits": wallet.credits,
    })


@csrf_exempt
@require_api_key("POST")
def create_purchase(request):
    from .serializers import PurchaseSerializer

    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        data = None

    serializer = PurchaseSerializer(data=data)
    if not serializer.is_valid():
        return error_response('invalid_credits', 'Credits must be a positive integer', 422)

    credits = serializer.validated_data["credits"]

    from .services import execute_purchase

    try:
        purchase = execute_purchase(request.api_user, credits)
    except ValueError as exc:
        if str(exc) != "insufficient_funds":
            raise
        return error_response('insufficient_funds', 'Insufficient balance', 409)

    return JsonResponse(
        {
            "purchase_id": purchase.id,
            "credits": purchase.credits,
            "amount": f"{purchase.amount:.2f}",
            "status": "completed",
        },
        status=201,
    )


@csrf_exempt
@require_api_key("GET")
def transaction_history(request):
    from django.core.paginator import Paginator
    from .models import Transfer, Purchase
    try:
        page_number = int(request.GET.get("page", "1"))
        page_size = int(request.GET.get("page_size", "20"))
        if page_number < 1 or not 1 <= page_size <= 100:
            raise ValueError()
    except ValueError:
        return error_response('invalid_pagination', 'Invalid page or page_size', 422)

    wallet, _ = Wallet.objects.get_or_create(user=request.api_user)
    items = []

    for deposit in Deposit.objects.filter(wallet=wallet):
        items.append({
            "type": "deposit",
            "id": deposit.id,
            "amount": f"{deposit.credited_amount:.2f}",
            "status": deposit.status,
            "created_at": deposit.created_at.isoformat(),
        })

    for transfer in Transfer.objects.filter(sender=wallet):
        items.append({
            "type": "transfer_out",
            "id": transfer.id,
            "amount": f"{transfer.amount:.2f}",
            "to_account_id": transfer.recipient_id,
            "status": "completed",
            "created_at": transfer.created_at.isoformat(),
        })

    for transfer in Transfer.objects.filter(recipient=wallet):
        items.append({
            "type": "transfer_in",
            "id": transfer.id,
            "amount": f"{transfer.amount:.2f}",
            "from_account_id": transfer.sender_id,
            "status": "completed",
            "created_at": transfer.created_at.isoformat(),
        })

    for purchase in Purchase.objects.filter(wallet=wallet):
        items.append({
            "type": "purchase",
            "id": purchase.id,
            "amount": f"{purchase.amount:.2f}",
            "credits": purchase.credits,
            "status": "completed",
            "created_at": purchase.created_at.isoformat(),
        })

    items.sort(key=lambda item: item["created_at"], reverse=True)
    paginator = Paginator(items, page_size)
    page = paginator.get_page(page_number)

    return JsonResponse({
        "results": list(page.object_list),
        "page": page_number,
        "page_size": page_size,
        "total": paginator.count,
    })
