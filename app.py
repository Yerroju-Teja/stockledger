import math
import os
from functools import wraps

from flask import (Flask, flash, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from db import (
    add_product, delete_product, get_all_products,
    get_dashboard_stats, get_low_stock_alerts,
    get_product_by_id, get_products_filtered,
    get_sales_report_data, get_today_sales_profit,
    get_user_by_username, create_user, record_sale, update_product
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me-in-production")

PER_PAGE = 10


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def role_required(*roles):
    """Usage: @role_required('admin', 'manager')"""
    def decorator(f):
        @wraps(f)
        @login_required
        def wrapper(*args, **kwargs):
            if session.get("role") not in roles:
                flash("You don't have permission to access that page.", "error")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Landing
# ---------------------------------------------------------------------------
@app.route("/")
def landing():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Auth — login
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Please fill in all fields.", "error")
            return render_template("login.html")

        user = get_user_by_username(username)

        if user and check_password_hash(user["password"], password):
            session["user"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password.", "error")

    return render_template("login.html")


# ---------------------------------------------------------------------------
# Auth — signup
# ---------------------------------------------------------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Please fill in all fields.", "error")
            return render_template("signup.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("signup.html")

        # Prevent duplicate usernames
        if get_user_by_username(username):
            flash("That username is already taken.", "error")
            return render_template("signup.html")

        hashed = generate_password_hash(password)
        create_user(username, hashed, role="staff")   # new users get 'staff', not 'admin'

        flash("Account created! You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")


# ---------------------------------------------------------------------------
# Auth — logout
# ---------------------------------------------------------------------------
@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    stats  = get_dashboard_stats()       # keys: total_products, total_value, low_stock_count
    alerts = get_low_stock_alerts()      # list of {name, quantity, min_stock}
    today  = get_today_sales_profit()    # keys: today_sales, today_profit

    return render_template(
        "dashboard.html",
        user=session["user"],
        stats=stats,
        alerts=alerts,
        today_sales=today["today_sales"],
        today_profit=today["today_profit"]
    )


# ---------------------------------------------------------------------------
# Products — list with search / filter / sort / pagination
# ---------------------------------------------------------------------------
@app.route("/products")
@login_required
def products():
    page      = request.args.get("page", 1, type=int)
    search    = request.args.get("q", "").strip()
    category  = request.args.get("category", "").strip()
    min_price = request.args.get("min_price", "").strip()
    max_price = request.args.get("max_price", "").strip()
    low_stock = request.args.get("low_stock")          # "1" or None
    sort      = request.args.get("sort", "")

    items, total, categories = get_products_filtered(
        search=search,
        category=category,
        min_price=min_price or None,
        max_price=max_price or None,
        low_stock=bool(low_stock),
        sort=sort,
        page=page,
        per_page=PER_PAGE
    )

    total_pages = max(1, math.ceil(total / PER_PAGE))

    return render_template(
        "products.html",
        products=items,      # shadowed below — keep variable name matching template
        page=page,
        total_pages=total_pages,
        search=search,
        categories=categories,
        category=category,
        min_price=min_price,
        max_price=max_price,
        low_stock=low_stock,
        sort=sort,
        
    )


# ---------------------------------------------------------------------------
# Products — add
# ---------------------------------------------------------------------------
@app.route("/add-product", methods=["GET", "POST"])
@login_required
def add_product_route():
    if request.method == "POST":
        f = request.form

        name           = f.get("name", "").strip()
        category       = f.get("category", "").strip()
        unit           = f.get("unit", "").strip()
        net_weight     = f.get("net_weight", "0")
        quantity       = f.get("quantity", "0")
        purchase_price = f.get("purchase_price", "0")
        selling_price  = f.get("selling_price", "0")
        min_stock      = f.get("min_stock", "5")

        if not name or not category or not unit:
            flash("Name, category and unit are required.", "error")
            return render_template("add_product.html")

        try:
            add_product(
                name=name,
                category=category,
                unit=unit,
                net_weight=float(net_weight),
                quantity=float(quantity),
                purchase_price=float(purchase_price),
                selling_price=float(selling_price),
                min_stock=int(min_stock)
            )
        except (ValueError, TypeError):
            flash("Please enter valid numbers for price, quantity, and weight.", "error")
            return render_template("add_product.html")

        flash(f'"{name}" added to inventory.', "success")
        return redirect(url_for("products"))

    return render_template("add_product.html")


# ---------------------------------------------------------------------------
# Products — edit
# ---------------------------------------------------------------------------
@app.route("/edit-product/<int:id>", methods=["GET", "POST"])
@login_required
def edit_product(id):
    product = get_product_by_id(id)
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("products"))

    if request.method == "POST":
        f = request.form

        name           = f.get("name", "").strip()
        category       = f.get("category", "").strip()
        unit_type      = f.get("unit_type", "").strip()
        quantity       = f.get("quantity", "0")
        min_stock      = f.get("min_stock", "5")
        purchase_price = f.get("purchase_price", "0")
        selling_price  = f.get("selling_price", "0")

        if not name or not category or not unit_type:
            flash("Name, category and unit are required.", "error")
            return render_template("edit_product.html", product=product)

        try:
            update_product(
                product_id=id,
                name=name,
                category=category,
                unit_type=unit_type,
                quantity=float(quantity),
                min_stock=int(min_stock),
                purchase_price=float(purchase_price),
                selling_price=float(selling_price)
            )
        except (ValueError, TypeError):
            flash("Please enter valid numbers for price and quantity.", "error")
            return render_template("edit_product.html", product=product)

        flash(f'"{name}" updated successfully.', "success")
        return redirect(url_for("products"))

    return render_template("edit_product.html", product=product)


# ---------------------------------------------------------------------------
# Products — delete  (POST-only to prevent accidental/CSRF deletion)
# ---------------------------------------------------------------------------
@app.route("/delete-product/<int:id>", methods=["POST"])
@login_required
def delete_product_route(id):
    product = get_product_by_id(id)
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("products"))

    delete_product(id)
    flash(f'"{product["name"]}" deleted.', "success")
    return redirect(url_for("products"))


# ---------------------------------------------------------------------------
# Sell
# ---------------------------------------------------------------------------
@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell_product():
    if request.method == "POST":
        product_id = request.form.get("product_id")
        qty_raw    = request.form.get("quantity")

        if not product_id or not qty_raw:
            flash("Please select a product and enter a quantity.", "error")
            return redirect(url_for("sell_product"))

        try:
            qty = float(qty_raw)
            if qty <= 0:
                raise ValueError
        except ValueError:
            flash("Please enter a valid quantity.", "error")
            return redirect(url_for("sell_product"))

        product = get_product_by_id(int(product_id))
        if not product:
            flash("Product not found.", "error")
            return redirect(url_for("sell_product"))

        if qty > product["quantity"]:
            flash(f'Not enough stock. Only {product["quantity"]} available.', "error")
            return redirect(url_for("sell_product"))

        selling_price = float(product["selling_price"])
        purchase_price = float(product["purchase_price"])

        amount = qty * selling_price
        profit = qty * (selling_price - purchase_price)

        success = record_sale(
            product_id=int(product_id),
            quantity=qty,
            amount=round(amount, 2),
            profit=round(profit, 2)
        )

        if success:
            flash(f'Sale recorded — ₹{amount:.2f} | Profit: ₹{profit:.2f}', "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Sale failed — stock may have changed. Please try again.", "error")
            return redirect(url_for("sell_product"))

    all_products = get_all_products()
    return render_template("sell.html", products=all_products)


# ---------------------------------------------------------------------------
# Sales report  (admin / manager only)
# ---------------------------------------------------------------------------
@app.route("/sales-report")
def sales_report():
    date_from = request.args.get("date_from", "").strip() or None
    date_to   = request.args.get("date_to",   "").strip() or None

    stats, sales, chart_daily, chart_top = get_sales_report_data(
        date_from=date_from,
        date_to=date_to
    )

    return render_template(
        "sales_report.html",
        stats=stats,
        sales=sales,
        chart_daily=chart_daily,
        chart_top=chart_top,
        date_from=date_from or "",
        date_to=date_to or ""
    )


# ---------------------------------------------------------------------------
# URL fix: the HTML uses url_for('add_product') not url_for('add_product_route')
# Flask needs the endpoint name to match.  We alias it here.
# ---------------------------------------------------------------------------
app.add_url_rule(
    "/add-product",
    endpoint="add_product",
    view_func=add_product_route,
    methods=["GET", "POST"]
)
app.add_url_rule(
    "/delete-product/<int:id>",
    endpoint="delete_product",
    view_func=delete_product_route,
    methods=["POST"]
)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    app.run(debug=debug_mode)
