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
        role = (r[0] or "client").strip()
        full_name = (r[1] or "").strip()
        if not full_name:
            full_name = login
        return UserContext(role=role, full_name=full_name)


def guest_context() -> UserContext:
    return UserContext(role="guest", full_name="")

