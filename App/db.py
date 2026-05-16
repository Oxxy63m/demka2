from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import MetaData, Table, create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from App.config import sqlalchemy_url
from App.paths import resource_path

_ENGINE: Engine | None = None
_SessionLocal: sessionmaker | None = None


def engine() -> Engine:
    global _ENGINE, _SessionLocal
    if _ENGINE is None:
        _ENGINE = create_engine(sqlalchemy_url(), future=True, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_ENGINE, autoflush=False, autocommit=False, future=True)
    return _ENGINE


def session() -> Session:
    if _SessionLocal is None:
        engine()
    assert _SessionLocal is not None
    return _SessionLocal()


@dataclass(frozen=True)
class Tables:
    suppliers: Table
    pickup_points: Table
    categories: Table
    statuses: Table
    users: Table
    products: Table
    orders: Table
    order_items: Table


_TABLES: Tables | None = None


def tables() -> Tables:
    global _TABLES
    if _TABLES is not None:
        return _TABLES
    md = MetaData()
    eng = engine()
    _TABLES = Tables(
        suppliers=Table("suppliers", md, autoload_with=eng),
        pickup_points=Table("pickup_points", md, autoload_with=eng),
        categories=Table("categories", md, autoload_with=eng),
        statuses=Table("statuses", md, autoload_with=eng),
        users=Table("users", md, autoload_with=eng),
        products=Table("products", md, autoload_with=eng),
        orders=Table("orders", md, autoload_with=eng),
        order_items=Table("order_items", md, autoload_with=eng),
    )
    return _TABLES


def resolve_product_photo_path(photo_value: str | None) -> str:
    """Возвращает существующий путь к картинке или заглушку resources/picture.png."""
    if not photo_value or not str(photo_value).strip():
        return resource_path("picture.png")
    p = str(photo_value).strip()
    # Абсолютный путь
    if os.path.isabs(p) and os.path.isfile(p):
        return p
    # Относительный путь от корня проекта
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    abs_rel = os.path.normpath(os.path.join(root, p))
    if os.path.isfile(abs_rel):
        return abs_rel
    # Файл из resources по имени
    r = resource_path(p)
    if os.path.isfile(r):
        return r
    return resource_path("picture.png")


_SEP_RE = re.compile(r"[,\n;\t]+")
_LINE_PAIR_RE = re.compile(r"^(\S+)\s+(\d+)\s*$")


def normalize_article(art: str) -> str:
    """Приводит артикул к виду для сравнения (пробелы, числовые артикулы «12345.0»)."""
    s = str(art or "").replace("\u00a0", " ").strip()
    if not s:
        return s
    try:
        f = float(s.replace(",", ".").replace(" ", ""))
        if f == int(f) and abs(f) < 1e15:
            return str(int(f))
    except ValueError:
        pass
    return s


def find_product_id_by_art(s: Session, art: str) -> int | None:
    norm = normalize_article(art)
    if not norm:
        return None
    t = tables()
    r = (
        s.execute(
            select(t.products.c.product_id).where(
                func.lower(func.trim(t.products.c.product_art)) == norm.lower()
            )
        )
        .scalar_one_or_none()
    )
    return int(r) if r is not None else None


def parse_order_line_items(text_value: str) -> list[tuple[str, int]]:
    """
    Парсит строку "артикул, кол-во, артикул, кол-во".
    Если количество пропущено/не число — берётся 1.
    Переносы строк считаются разделителями.
    """
    if text_value is None:
        return []
    raw = str(text_value).strip()
    if not raw:
        return []
    raw = raw.replace("\r", "\n")
    if "\n" in raw:
        out: list[tuple[str, int]] = []
        for line in raw.split("\n"):
            line = line.strip()
            if line:
                out.extend(parse_order_line_items(line))
        return out

    m = _LINE_PAIR_RE.match(raw)
    if m:
        return [(m.group(1), int(m.group(2)))]

    parts = [p.strip() for p in _SEP_RE.split(raw) if p is not None and str(p).strip()]
    out: list[tuple[str, int]] = []
    i = 0
    while i < len(parts):
        art = parts[i].strip()
        qty = 1
        if i + 1 < len(parts):
            try:
                qty_try = int(float(parts[i + 1].replace(" ", "")))
                if qty_try > 0:
                    qty = qty_try
                    i += 1
            except (TypeError, ValueError):
                pass
        if art:
            out.append((art, qty))
        i += 1
    return out


def get_or_create_simple_name_id(
    s: Session, table: Table, id_col: str, name_col: str, name: str | None
) -> int | None:
    if not name or not str(name).strip():
        return None
    name = str(name).strip()
    idc = getattr(table.c, id_col)
    nc = getattr(table.c, name_col)
    r = s.execute(select(idc).where(text(f"TRIM({name_col}) = :n")).params(n=name)).scalar_one_or_none()
    if r is not None:
        return int(r)
    try:
        new_id = s.execute(table.insert().values({name_col: name}).returning(idc)).scalar_one()
        return int(new_id)
    except SQLAlchemyError:
        s.rollback()
        raise


def product_has_orders(s: Session, product_id: int) -> bool:
    t = tables()
    q = select(t.order_items.c.order_item_id).where(t.order_items.c.product_id == product_id).limit(1)
    return s.execute(q).first() is not None


def order_article_summary(s: Session, order_id: int) -> str:
    """
    Короткая строка по позициям заказа: "ART1 x2, ART2 x1".
    """
    t = tables()
    q = (
        select(t.products.c.product_art, t.order_items.c.product_quantity)
        .select_from(t.order_items.join(t.products, t.products.c.product_id == t.order_items.c.product_id))
        .where(t.order_items.c.order_id == order_id)
        .order_by(t.order_items.c.order_item_id.asc())
    )
    items = s.execute(q).all()
    if not items:
        return "—"
    return ", ".join([f"{art} x{qty}" for art, qty in items])

