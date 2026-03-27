import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()


def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "inventory_user"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "inventory_db")
    )


# ── users ─────────────────────────────────────────────────────────────────────
def get_user_by_username(username):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        return cursor.fetchone()
    finally:
        cursor.close(); conn.close()


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
        cursor.close(); conn.close()


# ── dashboard ─────────────────────────────────────────────────────────────────
def get_dashboard_stats():
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS total_products FROM products")
        total_products = cursor.fetchone()["total_products"]
        cursor.execute(
            "SELECT IFNULL(SUM(quantity * selling_price), 0) AS total_value FROM products"
        )
        total_value = float(cursor.fetchone()["total_value"])
        cursor.execute(
            "SELECT COUNT(*) AS low_stock_count FROM products WHERE quantity <= min_stock"
        )
        low_stock_count = cursor.fetchone()["low_stock_count"]
        return {
            "total_products":  total_products,
            "total_value":     total_value,
            "low_stock_count": low_stock_count
        }
    finally:
        cursor.close(); conn.close()


def get_low_stock_alerts():
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT name, quantity, min_stock FROM products "
            "WHERE quantity <= min_stock ORDER BY quantity ASC"
        )
        return cursor.fetchall()
    finally:
        cursor.close(); conn.close()


def get_today_sales_profit():
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # works with both old (amount/profit cols) and new (total_amount/total_profit) schemas
        # tries old schema first; falls back gracefully via IFNULL
        cursor.execute("""
            SELECT
                IFNULL(SUM(amount),  0) AS today_sales,
                IFNULL(SUM(profit),  0) AS today_profit
            FROM sales
            WHERE DATE(created_at) = CURDATE()
        """)
        row = cursor.fetchone()
        return {
            "today_sales":  float(row["today_sales"]),
            "today_profit": float(row["today_profit"])
        }
    finally:
        cursor.close(); conn.close()


# ── products ──────────────────────────────────────────────────────────────────
def get_products_filtered(search="", category="", min_price=None,
                           max_price=None, low_stock=False,
                           sort="", page=1, per_page=10):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        conditions = ["1=1"]; params = []
        if search:
            conditions.append("(name LIKE %s OR category LIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])
        if category:
            conditions.append("category = %s"); params.append(category)
        if min_price not in (None, ""):
            conditions.append("selling_price >= %s"); params.append(min_price)
        if max_price not in (None, ""):
            conditions.append("selling_price <= %s"); params.append(max_price)
        if low_stock:
            conditions.append("quantity <= min_stock")
        where = " AND ".join(conditions)
        cursor.execute(
            f"SELECT COUNT(*) AS cnt FROM products WHERE {where}", tuple(params)
        )
        total = cursor.fetchone()["cnt"]
        order = {
            "price_asc":  "selling_price ASC",
            "price_desc": "selling_price DESC",
            "qty_asc":    "quantity ASC",
            "qty_desc":   "quantity DESC"
        }.get(sort, "id DESC")
        offset = (page - 1) * per_page
        cursor.execute(
            f"SELECT * FROM products WHERE {where} ORDER BY {order} LIMIT %s OFFSET %s",
            tuple(params) + (per_page, offset)
        )
        products = cursor.fetchall()
        cursor.execute("SELECT DISTINCT category FROM products ORDER BY category")
        categories = cursor.fetchall()
        return products, total, categories
    finally:
        cursor.close(); conn.close()


def get_product_by_id(product_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
        return cursor.fetchone()
    finally:
        cursor.close(); conn.close()


def get_all_products():
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, name, unit, quantity, purchase_price, selling_price "
            "FROM products ORDER BY name ASC"
        )
        return cursor.fetchall()
    finally:
        cursor.close(); conn.close()


def add_product(name, category, unit, net_weight,
                quantity, purchase_price, selling_price, min_stock):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO products
              (name, category, unit, net_weight, quantity,
               purchase_price, selling_price, min_stock)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (name, category, unit, net_weight,
              quantity, purchase_price, selling_price, min_stock))
        conn.commit()
    finally:
        cursor.close(); conn.close()


def update_product(product_id, name, category, unit_type,
                   quantity, min_stock, purchase_price, selling_price):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE products SET
              name=%s, category=%s, unit_type=%s, quantity=%s,
              min_stock=%s, purchase_price=%s, selling_price=%s
            WHERE id=%s
        """, (name, category, unit_type, quantity,
              min_stock, purchase_price, selling_price, product_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close(); conn.close()


def delete_product(product_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close(); conn.close()


# ── sales ─────────────────────────────────────────────────────────────────────
def record_sale(product_id, quantity, amount, profit):
    """Single-product sale. Locks row, checks stock, writes atomically."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT quantity FROM products WHERE id = %s FOR UPDATE", (product_id,)
        )
        product = cursor.fetchone()
        if not product or quantity > float(product["quantity"]):
            return False
        cursor.execute(
            "INSERT INTO sales (product_id, quantity_sold, amount, profit) "
            "VALUES (%s, %s, %s, %s)",
            (product_id, quantity, amount, profit)
        )
        cursor.execute(
            "UPDATE products SET quantity = quantity - %s WHERE id = %s",
            (quantity, product_id)
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback(); raise
    finally:
        cursor.close(); conn.close()


# ── sales report ──────────────────────────────────────────────────────────────
def get_sales_report_data(date_from=None, date_to=None):
    """
    Returns (stats, sales, chart_daily, chart_top).

    sales rows have keys: id, product_name, quantity_sold, amount, profit, created_at
    stats keys: total_revenue, total_profit, total_units, total_transactions
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)

        cond = ["1=1"]; params = []
        if date_from:
            cond.append("DATE(s.created_at) >= %s"); params.append(date_from)
        if date_to:
            cond.append("DATE(s.created_at) <= %s"); params.append(date_to)
        where = " AND ".join(cond)

        # ── summary stats ──────────────────────────────────────────────────
        cursor.execute(f"""
            SELECT
                IFNULL(SUM(s.amount),        0) AS total_revenue,
                IFNULL(SUM(s.profit),        0) AS total_profit,
                IFNULL(SUM(s.quantity_sold), 0) AS total_units,
                COUNT(s.id)                      AS total_transactions
            FROM sales s
            WHERE {where}
        """, tuple(params))
        row = cursor.fetchone()
        stats = {
            "total_revenue":      float(row["total_revenue"]),
            "total_profit":       float(row["total_profit"]),
            "total_units":        float(row["total_units"]),
            "total_transactions": int(row["total_transactions"])
        }

        # ── full sales list — exact columns sales_report.html uses ─────────
        cursor.execute(f"""
            SELECT
                s.id,
                p.name          AS product_name,
                s.quantity_sold,
                s.amount,
                s.profit,
                s.created_at
            FROM sales s
            JOIN products p ON s.product_id = p.id
            WHERE {where}
            ORDER BY s.created_at DESC
        """, tuple(params))
        sales = cursor.fetchall()

        # ── daily chart ────────────────────────────────────────────────────
        cursor.execute(f"""
            SELECT
                DATE(s.created_at)             AS day,
                IFNULL(SUM(s.amount), 0)       AS revenue,
                IFNULL(SUM(s.profit), 0)       AS profit
            FROM sales s
            WHERE {where}
            GROUP BY DATE(s.created_at)
            ORDER BY day ASC
        """, tuple(params))
        daily = cursor.fetchall()
        chart_daily = {
            "labels":  [str(r["day"])       for r in daily],
            "revenue": [float(r["revenue"]) for r in daily],
            "profit":  [float(r["profit"])  for r in daily],
        }

        # ── top 5 products by revenue ──────────────────────────────────────
        cursor.execute(f"""
            SELECT
                p.name                   AS product_name,
                IFNULL(SUM(s.amount), 0) AS revenue
            FROM sales s
            JOIN products p ON s.product_id = p.id
            WHERE {where}
            GROUP BY s.product_id, p.name
            ORDER BY revenue DESC
            LIMIT 5
        """, tuple(params))
        top = cursor.fetchall()
        chart_top = {
            "labels":  [r["product_name"]   for r in top],
            "revenue": [float(r["revenue"])  for r in top],
        }

        return stats, sales, chart_daily, chart_top

    finally:
        cursor.close(); conn.close()
