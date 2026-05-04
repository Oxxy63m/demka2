from __future__ import annotations

# Импорт данных из Excel в БД (как в проекте ранее).
# Запуск из корня: python import_to_db.py
# Файлы клади в папку resources/ (DATA_DIR в App.config):
#   user_import.xlsx, Tovar.xlsx, Заказ_import.xlsx, Пункты выдачи_import.xlsx
# Позиции заказа (order_items) создаются из строки Заказ_import: колонка со строкой артикулов
#   («Строка заказа» / «Артикул заказа» / …) или пары «Номер товара» + «Количество».
#
# pip install pandas openpyxl psycopg2-binary

import os
import sys

import pandas as pd
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from App.config import DB_CONFIG, DATA_DIR
from App.db import parse_order_line_items

_ROOT = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.normpath(os.path.join(_ROOT, DATA_DIR))

PATH_USERS = os.path.join(_DATA, "user_import.xlsx")
PATH_PRODUCTS = os.path.join(_DATA, "Tovar.xlsx")
PATH_ORDERS = os.path.join(_DATA, "Заказ_import.xlsx")
PATH_POINTS = os.path.join(_DATA, "Пункты выдачи_import.xlsx")

# Роль из Excel → значение в БД (users.user_role)
ROLE = {"администратор": "administrator", "менеджер": "manager", "клиент": "client"}


def _cur(conn):
    return conn.cursor()


def get_or_create_supplier_id_conn(conn, name):
    if name is None or (isinstance(name, float) and pd.isna(name)) or not str(name).strip():
        return None
    name = str(name).strip()
    cur = _cur(conn)
    cur.execute("SELECT supp_id FROM suppliers WHERE TRIM(supp_name)=%s", (name,))
    r = cur.fetchone()
    if r:
        cur.close()
        return r[0]
    cur.execute("INSERT INTO suppliers (supp_name) VALUES (%s) RETURNING supp_id", (name,))
    sid = cur.fetchone()[0]
    cur.close()
    return sid


def get_or_create_category_id_conn(conn, name):
    if name is None or (isinstance(name, float) and pd.isna(name)) or not str(name).strip():
        return None
    name = str(name).strip()
    cur = _cur(conn)
    cur.execute("SELECT categ_id FROM categories WHERE TRIM(categ_name)=%s", (name,))
    r = cur.fetchone()
    if r:
        cur.close()
        return r[0]
    cur.execute("INSERT INTO categories (categ_name) VALUES (%s) RETURNING categ_id", (name,))
    cid = cur.fetchone()[0]
    cur.close()
    return cid


def get_or_create_pickup_point_id_conn(conn, address: str | None):
    if not address or not str(address).strip():
        return None
    address = str(address).strip()
    cur = _cur(conn)
    cur.execute("SELECT pp_id FROM pickup_points WHERE TRIM(pp_name)=%s", (address,))
    r = cur.fetchone()
    if r:
        cur.close()
        return r[0]
    cur.execute("INSERT INTO pickup_points (pp_name) VALUES (%s) RETURNING pp_id", (address,))
    pid = cur.fetchone()[0]
    cur.close()
    return pid


def get_or_create_status_id_conn(conn, name: str | None):
    if not name or not str(name).strip():
        return None
    name = str(name).strip()
    cur = _cur(conn)
    cur.execute("SELECT status_id FROM statuses WHERE TRIM(status_name)=%s", (name,))
    r = cur.fetchone()
    if r:
        cur.close()
        return r[0]
    cur.execute("INSERT INTO statuses (status_name) VALUES (%s) RETURNING status_id", (name,))
    sid = cur.fetchone()[0]
    cur.close()
    return sid


def load_pickup_addresses(path_to_file):
    """Первый столбец — адреса; индекс 0 = номер 1 в Excel для заказов."""
    if not os.path.isfile(path_to_file):
        return []
    df = pd.read_excel(path_to_file, header=None)
    addresses = []
    for row_index in range(len(df)):
        address = str(df.iloc[row_index, 0]).strip()
        if address and address.lower() != "nan":
            addresses.append(address)
    print(f"Загружено пунктов выдачи: {len(addresses)}")
    return addresses


def import_users(connection, path_to_file):
    if not os.path.isfile(path_to_file):
        print(f"Нет файла пользователей: {path_to_file}")
        return 0
    df = pd.read_excel(path_to_file)
    cur = _cur(connection)
    n = 0
    for _, user_row in df.iterrows():
        login = str(user_row.get("Логин", "") or "").strip()
        if not login:
            continue
        role_ru = str(user_row.get("Роль сотрудника", "клиент") or "клиент").strip().lower()
        role_name = ROLE.get(role_ru, role_ru)
        full_name = str(user_row.get("ФИО", "") or "").strip()
        pwd = str(user_row.get("Пароль", "") or "").strip()
        # В новой схеме UNIQUE по логину не задан, поэтому делаем руками.
        cur.execute("SELECT user_id FROM users WHERE TRIM(user_login)=%s", (login,))
        if cur.fetchone():
            continue
        cur.execute(
            "INSERT INTO users (user_role, user_name, user_login, user_password) VALUES (%s,%s,%s,%s)",
            (role_name, full_name, login, pwd),
        )
        n += 1
    cur.close()
    print(f"Обработано строк пользователей: {n}")
    return n


def import_products(connection, path_to_file):
    if not os.path.isfile(path_to_file):
        print(f"Нет файла товаров: {path_to_file}")
        return 0
    df = pd.read_excel(path_to_file)
    cur = _cur(connection)
    n = 0
    for _, product_row in df.iterrows():
        product_name = product_row.get("Наименование товара")
        if pd.isna(product_name) or not str(product_name).strip():
            continue
        photo_filename = product_row.get("Фото")
        if pd.isna(photo_filename) or not str(photo_filename).strip():
            photo_filename = "picture.png"
        else:
            photo_filename = str(photo_filename).strip()
        price = product_row.get("Цена")
        price = float(price) if price is not None and not pd.isna(price) else 0
        discount = product_row.get("Действующая скидка")
        discount = float(discount) if discount is not None and not pd.isna(discount) else 0
        stock_quantity = product_row.get("Кол-во на складе")
        stock_quantity = int(float(stock_quantity)) if stock_quantity is not None and not pd.isna(stock_quantity) else 0
        article = product_row.get("Артикул")
        if pd.isna(article) or not str(article).strip():
            continue
        article = str(article).strip()
        supplier_id = get_or_create_supplier_id_conn(connection, product_row.get("Поставщик"))
        category_id = get_or_create_category_id_conn(connection, product_row.get("Категория товара"))
        manufacturer = str(product_row.get("Производитель") or "").strip() or None
        unit_name = str(product_row.get("Единица измерения") or "шт.").strip() or "шт."
        cur.execute(
            """
            INSERT INTO products (
                product_art, product_name, product_unit, product_price, supp_id,
                product_manufac, categ_id, product_discount, product_stock, product_desc, product_photo
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """,
            (
                article,
                str(product_name).strip(),
                unit_name,
                price,
                supplier_id,
                manufacturer,
                category_id,
                int(float(discount or 0)),
                stock_quantity,
                product_row.get("Описание товара"),
                photo_filename,
            ),
        )
        n += 1
    cur.close()
    print(f"Импорт/обновление товаров: {n}")
    return n


def _excel_cell_text(row: pd.Series, *column_names: str):
    """Первое непустое значение из списка имён колонок."""
    for name in column_names:
        if name not in row.index:
            continue
        v = row.get(name)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        s = str(v).strip()
        if s and s.lower() != "nan":
            return s
    return None


def add_order_items_from_excel_row(cur, order_id: int, order_row: pd.Series) -> int:
    """
    Заполняет order_items из той же строки Excel, что и заказ.
    Приоритет: текст «артикул, кол-во, …»; иначе «Номер товара» + «Количество».
    """
    n = 0
    line = _excel_cell_text(
        order_row,
        "Строка заказа",
        "Артикул заказа",
        "Состав заказа",
        "Позиции",
    )
    if line:
        for art, qty in parse_order_line_items(line):
            cur.execute("SELECT product_id FROM products WHERE TRIM(product_art)=%s", (art.strip(),))
            r = cur.fetchone()
            if not r:
                print(f"  заказ {order_id}: артикул «{art}» не найден — позиция пропущена")
                continue
            cur.execute(
                "INSERT INTO order_items (order_id, product_id, product_quantity) VALUES (%s, %s, %s)",
                (order_id, r[0], qty),
            )
            n += 1
        return n

    pid_raw = order_row.get("Номер товара")
    if pid_raw is None or (isinstance(pid_raw, float) and pd.isna(pid_raw)):
        return 0
    try:
        product_id = int(float(pid_raw))
    except (TypeError, ValueError):
        return 0
    qty_raw = order_row.get("Количество", 1)
    qty = int(float(qty_raw)) if qty_raw is not None and not pd.isna(qty_raw) else 1
    if qty < 1:
        qty = 1
    cur.execute(
        "INSERT INTO order_items (order_id, product_id, product_quantity) VALUES (%s, %s, %s)",
        (order_id, product_id, qty),
    )
    return 1


def _receiver_code_str(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        if isinstance(val, float) and val == int(val):
            return str(int(val))
        return str(int(float(val)))
    except (TypeError, ValueError):
        s = str(val).strip()
        return s if s else None


def import_orders(connection, path_to_file, pickup_addresses):
    if not os.path.isfile(path_to_file):
        print(f"Нет файла заказов: {path_to_file}")
        return 0
    df = pd.read_excel(path_to_file)
    cur = _cur(connection)
    imported = 0
    for _, order_row in df.iterrows():
        order_date = pd.to_datetime(order_row["Дата заказа"], errors="coerce")
        if pd.isna(order_date):
            print(f"Пропуск заказа: неверная дата ({order_row.get('Дата заказа')})")
            continue
        order_date = order_date.date()

        pup_date = pd.to_datetime(order_row["Дата доставки"], errors="coerce")
        pup_date = pup_date.date() if not pd.isna(pup_date) else None

        client_full_name = str(order_row.get("ФИО авторизированного клиента") or "").strip()
        if not client_full_name:
            # в новой схеме orders.user_name обязателен по смыслу, но в DDL NULL разрешён — всё равно ставим заглушку
            client_full_name = "—"

        pickup_point_value = order_row["Адрес пункта выдачи"]
        pickup_address_string = None
        if pickup_addresses and pickup_point_value is not None and not pd.isna(pickup_point_value):
            try:
                pickup_index = int(float(pickup_point_value))
                if 1 <= pickup_index <= len(pickup_addresses):
                    pickup_address_string = pickup_addresses[pickup_index - 1]
            except (TypeError, ValueError):
                pickup_address_string = str(pickup_point_value).strip() if str(pickup_point_value).strip() else None
        elif pickup_point_value is not None and not pd.isna(pickup_point_value):
            pickup_address_string = str(pickup_point_value).strip()

        receiver_code = _receiver_code_str(order_row.get("Код для получения"))

        status = str(order_row.get("Статус заказа", "") or "").strip() or None
        pickup_point_id = (
            get_or_create_pickup_point_id_conn(connection, pickup_address_string) if pickup_address_string else None
        )
        status_id = get_or_create_status_id_conn(connection, status)

        cur.execute(
            """
            INSERT INTO orders (order_date, order_pup_date, pp_id, user_name, order_pp_code, status_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING order_id;
            """,
            (
                order_date,
                pup_date,
                pickup_point_id,
                client_full_name,
                int(receiver_code) if receiver_code is not None and receiver_code != "" else None,
                status_id,
            ),
        )
        order_id = cur.fetchone()[0]
        k = add_order_items_from_excel_row(cur, order_id, order_row)
        if k == 0:
            print(f"  заказ {order_id}: нет позиций (добавьте «Строка заказа»/«Артикул заказа» или «Номер товара»)")
        imported += 1
    cur.close()
    print(f"Импортировано заказов: {imported}")
    return imported


def main():
    print(f"Папка данных: {_DATA}\n")
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        pickup_addresses = load_pickup_addresses(PATH_POINTS)
        import_users(conn, PATH_USERS)
        import_products(conn, PATH_PRODUCTS)
        import_orders(conn, PATH_ORDERS, pickup_addresses)
        conn.commit()
        print("\nИмпорт завершён.")
    except Exception as e:
        conn.rollback()
        print(f"\nОшибка: {e}")
        import traceback

        traceback.print_exc()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
