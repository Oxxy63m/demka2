from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, text

from App.db import session, tables


@dataclass(frozen=True)
class UserContext:
    role: str  # guest/client/manager/administrator
    full_name: str


ROLE_LABEL = {
    "guest": "Гость",
    "client": "Клиент",
    "manager": "Менеджер",
    "administrator": "Администратор",
}


def _normalize_role(raw: str | None) -> str:
    """Приводит роль из БД к одному из guest/client/manager/administrator."""
    s = (raw or "").strip().lower()
    if not s:
        return "client"
    ru = {"администратор": "administrator", "менеджер": "manager", "клиент": "client", "гость": "guest"}
    if s in ru:
        return ru[s]
    if s in ("administrator", "manager", "client", "guest"):
        return s
    if s in ("admin", "админ"):
        return "administrator"
    return "client"


def authenticate(login: str, password: str) -> UserContext | None:
    login = (login or "").strip()
    password = (password or "").strip()
    if not login or not password:
        return None
    t = tables()
    with session() as s:
        q = (
            select(t.users.c.user_role, t.users.c.user_name)
            .where(text("TRIM(user_login) = :l"))
            .where(text("user_password = :p"))
            .params(l=login, p=password)
        )
        r = s.execute(q).first()
        if not r:
            return None
        role = _normalize_role(r[0])
        full_name = (r[1] or "").strip()
        if not full_name:
            full_name = login
        return UserContext(role=role, full_name=full_name)


def guest_context() -> UserContext:
    return UserContext(role="guest", full_name="")

