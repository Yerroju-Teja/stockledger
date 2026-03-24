import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

# ======================
# CONNECTION
# ======================
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "inventory_user"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "inventory_db")
    )


# ======================
# USERS
# ======================
def get_user_by_username(username):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def create_user(username, hashed_password, role="staff"):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
            (username, hashed_password, role)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# ======================
# DASHBOARD STATS
# ======================
def get_dashboard_stats():
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS total_products FROM products")
        total_products = cursor.fetchone()["total_products"]

        cursor.execute("""
            SELECT IFNULL(SUM(quantity * selling_price), 0) AS total_value
            FROM products
        """)
        total_value = float(cursor.fetchone()["total_value"])

        cursor.execute("""
            SELECT COUNT(*) AS low_stock_count
            FROM products WHERE quantity <= min_stock
        """)
        low_stock_count = cursor.fetchone()["low_stock_count"]

        return {
            "total_products": total_products,
            "total_value": total_value,
            "low_stock_count": low_stock_count
        }
    finally:
        cursor.close()
        conn.close()


def get_low_stock_alerts():
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT name, quantity, min_stock
            FROM products
            WHERE quantity <= min_stock
            ORDER BY quantity ASC
        """)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_today_sales_profit():
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                IFNULL(SUM(amount), 0)  AS today_sales,
                IFNULL(SUM(profit), 0)  AS today_profit
            FROM sales
            WHERE DATE(created_at) = CURDATE()
        """)
        row = cursor.fetchone()
        return {
            "today_sales":  float(row["today_sales"]),
            "today_profit": float(row["today_profit"])
        }
    finally:
        cursor.close()
        conn.close()


# ======================
# PRODUCTS — read
# ======================
def get_products_filtered(search="", category="", min_price="",
                           max_price="", low_stock=False,
                           sort="", page=1, per_page=10):
    """
    Returns (products_for_page, total_count, categories_list).
    Pagination is done in SQL with LIMIT / OFFSET.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)

        # ---- base filter (reused for COUNT and data queries) ----
        conditions = ["1=1"]
        params = []

        if search:
            conditions.append("(name LIKE %s OR category LIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])
        if category:
            conditions.append("category = %s")
            params.append(category)
        if min_price != "" and min_price is not None:
            conditions.append("selling_price >= %s")
            params.append(min_price)
        if max_price != "" and max_price is not None:
            conditions.append("selling_price <= %s")
            params.append(max_price)
        if low_stock:
            conditions.append("quantity <= min_stock")

        where = " AND ".join(conditions)

        # ---- total count for pagination ----
        cursor.execute(f"SELECT COUNT(*) AS cnt FROM products WHERE {where}", tuple(params))
        total = cursor.fetchone()["cnt"]

        # ---- sort ----
        order_map = {
            "price_asc":  "selling_price ASC",
            "price_desc": "selling_price DESC",
            "qty_asc":    "quantity ASC",
            "qty_desc":   "quantity DESC",
        }
        order = order_map.get(sort, "id DESC")

        # ---- paginated data ----
        offset = (page - 1) * per_page
        data_params = list(params) + [per_page, offset]
        cursor.execute(
            f"SELECT * FROM products WHERE {where} ORDER BY {order} LIMIT %s OFFSET %s",
            tuple(data_params)
        )
        products = cursor.fetchall()

        # ---- category list for filter dropdown ----
        cursor.execute("SELECT DISTINCT category FROM products ORDER BY category")
        categories = cursor.fetchall()

        return products, total, categories
    finally:
        cursor.close()
        conn.close()


def get_product_by_id(product_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def get_all_products():
    """Lightweight list used by the Sell page dropdown."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, name, unit, quantity, purchase_price, selling_price "
            "FROM products ORDER BY name ASC"
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# ======================
# PRODUCTS — write
# ======================
def add_product(name, category, unit, net_weight,
                quantity, purchase_price, selling_price, min_stock):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO products
              (name, category, unit, net_weight,
               quantity, purchase_price, selling_price, min_stock)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (name, category, unit, net_weight,
              quantity, purchase_price, selling_price, min_stock))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def update_product(product_id, name, category, unit_type,
                   quantity, min_stock, purchase_price, selling_price):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE products SET
              name           = %s,
              category       = %s,
              unit_type      = %s,
              quantity       = %s,
              min_stock      = %s,
              purchase_price = %s,
              selling_price  = %s
            WHERE id = %s
        """, (name, category, unit_type,
              quantity, min_stock, purchase_price, selling_price,
              product_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


def delete_product(product_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


# ======================
# SALES
# ======================
def record_sale(product_id, quantity, amount, profit):
    """
    Inserts a sales record and decrements stock in one transaction.
    Returns True on success, False if stock is insufficient.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)

        # Lock the row and re-check stock inside the transaction
        cursor.execute(
            "SELECT quantity, selling_price, purchase_price "
            "FROM products WHERE id = %s FOR UPDATE",
            (product_id,)
        )
        product = cursor.fetchone()
        if not product or quantity > product["quantity"]:
            return False

        cursor.execute("""
            INSERT INTO sales (product_id, quantity_sold, amount, profit)
            VALUES (%s, %s, %s, %s)
        """, (product_id, quantity, amount, profit))

        cursor.execute(
            "UPDATE products SET quantity = quantity - %s WHERE id = %s",
            (quantity, product_id)
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


# ======================
# SALES REPORT
# ======================
def get_sales_report(limit=50):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                s.id,
                p.name          AS product_name,
                s.quantity_sold,
                s.amount,
                s.profit,
                s.created_at
            FROM sales s
            JOIN products p ON s.product_id = p.id
            ORDER BY s.created_at DESC
            LIMIT %s
        """, (limit,))
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
