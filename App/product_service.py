from __future__ import annotations

import os
import shutil
import uuid
from decimal import Decimal

from sqlalchemy import Select, delete, func, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from App.db import get_or_create_simple_name_id, product_has_orders, session, tables
from App.paths import app_images_dir


def list_suppliers() -> list[str]:
    t = tables()
    with session() as s:
        q = select(t.suppliers.c.supp_name).order_by(func.lower(t.suppliers.c.supp_name).asc())
        return [str(x[0]).strip() for x in s.execute(q).all() if x[0] is not None and str(x[0]).strip()]


def list_categories() -> list[str]:
    t = tables()
    with session() as s:
        q = select(t.categories.c.categ_name).order_by(func.lower(t.categories.c.categ_name).asc())
        return [str(x[0]).strip() for x in s.execute(q).all() if x[0] is not None and str(x[0]).strip()]


def list_manufacturers() -> list[str]:
    t = tables()
    m = t.products.c.product_manufac
    with session() as s:
        # DISTINCT + ORDER BY lower(...) недопустим в PostgreSQL без включения lower в SELECT;
        # GROUP BY даёт те же уникальные значения и позволяет сортировку без регистра.
        q = (
            select(m)
            .where(m.isnot(None))
            .where(func.trim(m) != "")
            .group_by(m)
            .order_by(func.lower(m).asc())
        )
        return [str(x[0]).strip() for x in s.execute(q).all() if x[0] is not None and str(x[0]).strip()]


def products_query(
    search: str | None = None,
    supplier_name: str | None = None,
    sort_stock: str | None = None,  # "asc" | "desc" | None
) -> Select:
    t = tables()
    q = (
        select(
            t.products.c.product_id,
            t.products.c.product_art,
            t.products.c.product_name,
            t.products.c.product_unit,
            t.products.c.product_price,
            t.products.c.product_manufac,
            t.products.c.product_discount,
            t.products.c.product_stock,
            t.products.c.product_desc,
            t.products.c.product_photo,
            t.categories.c.categ_name,
            t.suppliers.c.supp_name,
        )
        .select_from(
            t.products.outerjoin(t.categories, t.categories.c.categ_id == t.products.c.categ_id).outerjoin(
                t.suppliers, t.suppliers.c.supp_id == t.products.c.supp_id
            )
        )
    )

    if supplier_name and supplier_name != "Все поставщики":
        q = q.where(text("TRIM(suppliers.supp_name) = :sn")).params(sn=supplier_name.strip())

    s = (search or "").strip()
    if s:
        like = f"%{s.lower()}%"
        q = q.where(
            func.lower(func.coalesce(t.products.c.product_name, "")).like(like)
            | func.lower(func.coalesce(t.products.c.product_art, "")).like(like)
            | func.lower(func.coalesce(t.products.c.product_desc, "")).like(like)
            | func.lower(func.coalesce(t.products.c.product_manufac, "")).like(like)
            | func.lower(func.coalesce(t.suppliers.c.supp_name, "")).like(like)
            | func.lower(func.coalesce(t.categories.c.categ_name, "")).like(like)
        )

    if sort_stock == "asc":
        q = q.order_by(t.products.c.product_stock.asc(), t.products.c.product_id.asc())
    elif sort_stock == "desc":
        q = q.order_by(t.products.c.product_stock.desc(), t.products.c.product_id.asc())
    else:
        q = q.order_by(t.products.c.product_id.asc())

    return q


def get_product(product_id: int) -> dict | None:
    t = tables()
    p = t.products.c
    with session() as s:
        q = (
            select(
                p.product_id,
                p.product_art,
                p.product_name,
                p.product_unit,
                p.product_price,
                p.product_manufac,
                p.product_discount,
                p.product_stock,
                p.product_desc,
                p.product_photo,
                p.categ_id,
                p.supp_id,
                t.categories.c.categ_name.label("categ_name"),
                t.suppliers.c.supp_name.label("supp_name"),
            )
            .select_from(
                t.products.outerjoin(t.categories, t.categories.c.categ_id == t.products.c.categ_id).outerjoin(
                    t.suppliers, t.suppliers.c.supp_id == t.products.c.supp_id
                )
            )
            .where(t.products.c.product_id == product_id)
        )
        r = s.execute(q).mappings().first()
        return dict(r) if r else None


def next_product_id() -> int:
    t = tables()
    with session() as s:
        mx = s.execute(select(func.max(t.products.c.product_id))).scalar_one()
        return int(mx or 0) + 1


def _save_image_to_app_folder(src_path: str) -> str:
    """
    Копирует файл в `app_images/` и возвращает относительный путь, который кладём в БД.
    Файл сохраняем как уникальный, чтобы избежать конфликтов имён.
    """
    dst_dir = app_images_dir()
    ext = os.path.splitext(src_path)[1].lower() or ".png"
    fname = f"{uuid.uuid4().hex}{ext}"
    dst_abs = os.path.join(dst_dir, fname)
    # Требование 300x200: если исходник больше — сохраняем уменьшенную копию.
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage

        img = QImage(src_path)
        if not img.isNull() and (img.width() > 300 or img.height() > 200):
            scaled = img.scaled(300, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            scaled.save(dst_abs)
        else:
            shutil.copyfile(src_path, dst_abs)
    except Exception:
        shutil.copyfile(src_path, dst_abs)
    # относительный путь от корня проекта
    return os.path.normpath(os.path.join("app_images", fname))


def delete_product_image_if_owned(photo_value: str | None) -> None:
    if not photo_value:
        return
    p = str(photo_value).strip()
    if not p:
        return
    # удаляем только если это файл из app_images
    if p.replace("\\", "/").startswith("app_images/") or p.replace("\\", "/").startswith("./app_images/"):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        abs_path = os.path.normpath(os.path.join(root, p))
        try:
            if os.path.isfile(abs_path):
                os.remove(abs_path)
        except OSError:
            pass


def upsert_product(
    *,
    product_id: int | None,
    article: str,
    name: str,
    category_name: str | None,
    description: str | None,
    manufacturer: str | None,
    supplier_name: str | None,
    price: float,
    unit: str,
    qty: int,
    discount: float,
    photo_path_to_copy: str | None,
) -> int:
    t = tables()
    with session() as s:
        try:
            supp_id = get_or_create_simple_name_id(s, t.suppliers, "supp_id", "supp_name", supplier_name)
            categ_id = get_or_create_simple_name_id(s, t.categories, "categ_id", "categ_name", category_name)

            photo_value: str | None = None
            if photo_path_to_copy:
                photo_value = _save_image_to_app_folder(photo_path_to_copy)

            payload = {
                "product_art": article.strip(),
                "product_name": name.strip(),
                "product_unit": (unit or "шт.").strip() or "шт.",
                "product_price": Decimal(str(price)),
                "supp_id": supp_id,
                "product_manufac": (manufacturer or "").strip() or None,
                "categ_id": categ_id,
                "product_discount": int(float(discount)),
                "product_stock": int(qty),
                "product_desc": (description or "").strip() or None,
            }

            if product_id is None:
                if photo_value is None:
                    photo_value = "picture.png"
                payload["product_photo"] = photo_value
                new_id = s.execute(t.products.insert().values(payload).returning(t.products.c.product_id)).scalar_one()
                s.commit()
                return int(new_id)

            # update existing
            old = s.execute(select(t.products.c.product_photo).where(t.products.c.product_id == product_id)).first()
            old_photo = old[0] if old else None
            if photo_value is not None:
                payload["product_photo"] = photo_value
            s.execute(update(t.products).where(t.products.c.product_id == product_id).values(payload))
            s.commit()
            if photo_value is not None and old_photo and str(old_photo).strip() != str(photo_value).strip():
                delete_product_image_if_owned(str(old_photo))
            return int(product_id)
        except SQLAlchemyError:
            s.rollback()
            raise


def delete_product(product_id: int) -> None:
    if product_id is None:
        return
    t = tables()
    with session() as s:
        if product_has_orders(s, int(product_id)):
            raise ValueError("Товар присутствует в заказах — удалить нельзя.")
        old = s.execute(select(t.products.c.product_photo).where(t.products.c.product_id == product_id)).first()
        old_photo = old[0] if old else None
        s.execute(delete(t.products).where(t.products.c.product_id == product_id))
        s.commit()
    if old_photo:
        delete_product_image_if_owned(str(old_photo))

