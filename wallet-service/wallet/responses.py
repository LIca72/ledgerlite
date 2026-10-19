from django.http import JsonResponse


def error_response(code, message, status):
    return JsonResponse(
        {
            "error": {
                "code": code,
                "message": message,
                "details": {},
            }
        },
        status=status,
    )
