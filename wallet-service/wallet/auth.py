import hashlib

from .models import APIKey


def get_user_by_api_key(request):
    raw_key = request.headers.get("X-API-Key", "")

    if not raw_key:
        return None

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    api_key = (
        APIKey.objects.select_related("user")
        .filter(key_hash=key_hash, user__is_active=True)
        .first()
    )

    return api_key.user if api_key else None


def require_api_key(method):
    from functools import wraps

    from .responses import error_response

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.method != method:
                return error_response(
                    "method_not_allowed",
                    f"{method} required",
                    405,
                )

            user = get_user_by_api_key(request)
            if user is None:
                return error_response(
                    "unauthorized",
                    "Invalid API key",
                    401,
                )

            request.api_user = user
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
