import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select

from app.config import settings

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


class ApiKey(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    name: str
    credits: int = Field(default=0)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CreditTransaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    api_key_id: int = Field(foreign_key="apikey.id")
    amount: int
    reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)


def get_api_key_by_key(session: Session, key: str) -> Optional[ApiKey]:
    return session.exec(select(ApiKey).where(ApiKey.key == key)).first()


def create_api_key(session: Session, name: str, initial_credits: int = 0) -> ApiKey:
    api_key = ApiKey(key=secrets.token_urlsafe(32), name=name, credits=initial_credits)
    session.add(api_key)
    session.commit()
    session.refresh(api_key)
    if initial_credits:
        session.add(CreditTransaction(api_key_id=api_key.id, amount=initial_credits, reason="initial grant"))
        session.commit()
    return api_key


def add_credits(session: Session, api_key: ApiKey, amount: int, reason: str) -> ApiKey:
    api_key.credits += amount
    session.add(api_key)
    session.add(CreditTransaction(api_key_id=api_key.id, amount=amount, reason=reason))
    session.commit()
    session.refresh(api_key)
    return api_key


def consume_credit(session: Session, api_key: ApiKey) -> bool:
    """Deduct one credit if available. SQLite serializes writers, so this is
    safe from double-spend even with concurrent requests on the same key."""
    row = session.exec(select(ApiKey).where(ApiKey.id == api_key.id, ApiKey.credits > 0)).first()
    if not row:
        return False
    row.credits -= 1
    session.add(row)
    session.add(CreditTransaction(api_key_id=row.id, amount=-1, reason="remove-background call"))
    session.commit()
    return True
