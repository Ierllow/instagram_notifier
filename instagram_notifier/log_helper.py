from django.db import transaction
from typing import Callable, Any
from functools import wraps
from instagram_notifier.models import ErrorLog

def log_error(location: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                with transaction.atomic():
                    ErrorLog.objects.create(location=location, message=str(e))
                raise
        return wrapper
    return decorator
