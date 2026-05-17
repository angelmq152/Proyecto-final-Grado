from collections.abc import Awaitable, Callable
from functools import wraps

import structlog

from lobster_agent.config import Settings

log = structlog.get_logger()


def is_allowed(event: object, settings: Settings) -> bool:
    user = getattr(event, "from_user", None)
    user_id = getattr(user, "id", None)
    if user_id in settings.telegram.allowed_user_ids:
        return True
    log.warning(
        "lobster.telegram.unauthorized",
        user_id=user_id,
        username=getattr(user, "username", None),
        telegram_event=getattr(event, "text", None) or getattr(event, "data", None),
    )
    return False


def whitelist_only(
    handler: Callable[..., Awaitable[object]],
) -> Callable[..., Awaitable[object | None]]:
    @wraps(handler)
    async def wrapper(*args: object, **kwargs: object) -> object | None:
        event = args[0] if args else kwargs.get("event")
        settings = kwargs.get("settings")
        if not isinstance(settings, Settings) or event is None:
            return await handler(*args, **kwargs)
        if not is_allowed(event, settings):
            return None
        return await handler(*args, **kwargs)

    return wrapper
