from functools import wraps
from typing import Callable
from django.conf import settings
from rest_framework.response import Response


def ai_protected(endpoint_type: str, plan_gate: bool = True):
    """Keep authenticated AI access while leaving all normal user actions unlimited."""

    def decorator(view_func: Callable):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not (settings.DEBUG or getattr(settings, 'AI_TEST_OPEN', False)):
                user = getattr(request, 'user', None)
                if not getattr(user, 'is_authenticated', False):
                    return Response({'error': 'unauthorized'}, status=401)
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
