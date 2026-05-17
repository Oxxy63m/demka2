from __future__ import annotations

from datetime import date

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from App.db import find_product_id_by_art, order_article_summary, parse_order_line_items, session, tables


def list_statuses() -> list[str]:
    t = tables()
    with session() as s:
        q = select(t.statuses.c.status_name).order_by(func.lower(t.statuses.c.status_name).asc())
        return [str(x[0]).strip() for x in s.execute(q).all() if x[0] is not None and str(x[0]).strip()]


def list_pickup_points() -> list[str]:
    t = tables()
    with session() as s:
        q = select(t.pickup_points.c.pp_name).order_by(func.lower(t.pickup_points.c.pp_name).asc())
        return [str(x[0]).strip() for x in s.execute(q).all() if x[0] is not None and str(x[0]).strip()]


def list_orders() -> list[dict]:
    t = tables()
    with session() as s:
        q = (
            select(
                t.orders.c.order_id,
                t.orders.c.order_date,
                t.orders.c.order_pup_date,
                t.orders.c.order_pp_code,
                t.orders.c.user_name,
                t.statuses.c.status_name,
                t.pickup_points.c.pp_name,
            )
            .select_from(
                t.orders.outerjoin(t.statuses, t.statuses.c.status_id == t.orders.c.status_id).outerjoin(
                    t.pickup_points, t.pickup_points.c.pp_id == t.orders.c.pp_id
                )
            )
            .order_by(t.orders.c.order_id.desc())
        )
        rows = s.execute(q).all()
        out: list[dict] = []
        for r in rows:
            out.append(
                {
                    "order_id": int(r[0]),
                    "order_date": r[1],
                    "order_pup_date": r[2],
                    "order_pp_code": r[3],
                    "user_name": r[4],
                    "status_name": r[5],
                    "pp_name": r[6],
                    "article_summary": order_article_summary(s, int(r[0])),
                }
            )
        return out


def get_order(order_id: int) -> dict | None:
    t = tables()
    c = t.orders.c
    with session() as s:
        o = (
            s.execute(
                select(
                    c.order_id,
                    c.order_date,
                    c.order_pup_date,
                    c.order_pp_code,
                    c.user_name,
                    c.status_id,
                    c.pp_id,
                    t.statuses.c.status_name.label("status_name"),
                    t.pickup_points.c.pp_name.label("pp_name"),
                )
                .select_from(
                    t.orders.outerjoin(t.statuses, t.statuses.c.status_id == t.orders.c.status_id).outerjoin(
                        t.pickup_points, t.pickup_points.c.pp_id == t.orders.c.pp_id
                    )
                )
                .where(t.orders.c.order_id == order_id)
            )
            .mappings()
            .first()
        )
        if not o:
            return None
        order = dict(o)
        q = (
            select(t.products.c.product_art, t.order_items.c.product_quantity)
            .select_from(t.order_items.join(t.products, t.products.c.product_id == t.order_items.c.product_id))
            .where(t.order_items.c.order_id == order_id)
            .order_by(t.order_items.c.order_item_id.asc())
        )
        items = s.execute(q).all()
        order["items"] = [{"art": art, "qty": int(qty)} for art, qty in items]
        return order


def _get_or_create_status_id(s, name: str | None) -> int | None:
    t = tables()
    if not name or not str(name).strip():
        return None
    name = str(name).strip()
    r = s.execute(select(t.statuses.c.status_id).where(func.trim(t.statuses.c.status_name) == name)).scalar_one_or_none()
    if r is not None:
        return int(r)
    new_id = s.execute(t.statuses.insert().values(status_name=name).returning(t.statuses.c.status_id)).scalar_one()
    return int(new_id)


def _sync_orders_id_sequence(s) -> None:
    """После импорта с явными ID выравнивает serial для orders."""
    s.execute(
        text(
            """
            SELECT setval(
                pg_get_serial_sequence('orders', 'order_id'),
                COALESCE((SELECT MAX(order_id) FROM orders), 0),
                true
            )
            """
        )
    )


def _sync_order_items_id_sequence(s) -> None:
    """После импорта выравнивает serial для order_items (иначе duplicate key на order_item_id)."""
    s.execute(
        text(
            """
            SELECT setval(
                pg_get_serial_sequence('order_items', 'order_item_id'),
                COALESCE((SELECT MAX(order_item_id) FROM order_items), 0),
                true
            )
            """
        )
    )


def _get_or_create_pickup_id(s, address: str | None) -> int | None:
    t = tables()
    if not address or not str(address).strip():
        return None
    address = str(address).strip()
    r = (
        s.execute(select(t.pickup_points.c.pp_id).where(func.trim(t.pickup_points.c.pp_name) == address))
        .scalar_one_or_none()
    )
    if r is not None:
        return int(r)
    new_id = s.execute(t.pickup_points.insert().values(pp_name=address).returning(t.pickup_points.c.pp_id)).scalar_one()
    return int(new_id)


def upsert_order(
    *,
    order_id: int | None,
    status_name: str | None,
    pickup_address: str | None,
    order_date: date,
    delivery_date: date | None,
    receiver_code: str | None,
    client_name: str,
    items_text: str,
) -> int:
    t = tables()
    with session() as s:
        try:
            status_id = _get_or_create_status_id(s, status_name)
            pp_id = _get_or_create_pickup_id(s, pickup_address)

            code_val = None
            rc = (receiver_code or "").strip()
            if rc:
                try:
                    code_val = int(rc)
                except ValueError:
                    raise ValueError("Код для получения должен быть числом.")

            payload = {
                "order_date": order_date,
                "order_pup_date": delivery_date,
                "pp_id": pp_id,
                "user_name": (client_name or "—").strip() or "—",
                "order_pp_code": code_val,
                "status_id": status_id,
            }

            if order_id is None:
                _sync_orders_id_sequence(s)
                new_id = s.execute(t.orders.insert().values(payload).returning(t.orders.c.order_id)).scalar_one()
                order_id = int(new_id)
            else:
                s.execute(update(t.orders).where(t.orders.c.order_id == order_id).values(payload))

            # позиции: полностью пересоздаём (редактирование и новый заказ)
            s.execute(delete(t.order_items).where(t.order_items.c.order_id == order_id))
            _sync_order_items_id_sequence(s)
            pairs = parse_order_line_items(items_text)
            if not pairs:
                if (items_text or "").strip():
                    raise ValueError(
                        "Не удалось разобрать позиции. Формат: артикул, количество, артикул, количество… "
                        "Или по одной паре «артикул количество» в строке."
                    )
                raise ValueError("Добавьте хотя бы одну позицию заказа (артикул и количество).")
            for art, qty in pairs:
                pid = find_product_id_by_art(s, art)
                if pid is None:
                    raise ValueError(f"Артикул «{art.strip()}» не найден в товарах.")
                s.execute(
                    t.order_items.insert().values(order_id=order_id, product_id=pid, product_quantity=int(qty))
                )

            s.commit()
            return int(order_id)
        except (SQLAlchemyError, ValueError):
            s.rollback()
            raise


def delete_order(order_id: int) -> None:
    t = tables()
    with session() as s:
        try:
            s.execute(delete(t.order_items).where(t.order_items.c.order_id == order_id))
            s.execute(delete(t.orders).where(t.orders.c.order_id == order_id))
            s.commit()
        except SQLAlchemyError:
            s.rollback()
            raise

