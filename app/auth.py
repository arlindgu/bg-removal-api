import hmac

from fastapi import Header, HTTPException, status

from app.config import settings
from app.db import ApiKey, get_api_key_by_key, get_session


def require_api_key(authorization: str = Header(...)) -> ApiKey:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    key = authorization.removeprefix("Bearer ").strip()

    with get_session() as session:
        api_key = get_api_key_by_key(session, key)
        if not api_key or not api_key.active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
        session.expunge(api_key)
        return api_key


def require_master_key(x_master_key: str = Header(...)) -> None:
    if not hmac.compare_digest(x_master_key, settings.api_master_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid master key")
