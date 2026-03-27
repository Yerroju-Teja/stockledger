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

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me-in-production")

PER_PAGE = 10


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def role_required(*roles):
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


@app.route("/")
def landing():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


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
        flash("Invalid username or password.", "error")
    return render_template("login.html")


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
        if get_user_by_username(username):
            flash("That username is already taken.", "error")
            return render_template("signup.html")
        create_user(username, generate_password_hash(password), role="staff")
        flash("Account created! You can now log in.", "success")
        return redirect(url_for("login"))
    return render_template("signup.html")


@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    stats  = get_dashboard_stats()
    alerts = get_low_stock_alerts()
    today  = get_today_sales_profit()
    return render_template(
        "dashboard.html",
        user=session["user"],
        stats=stats,
        alerts=alerts,
        today_sales=today["today_sales"],
        today_profit=today["today_profit"]
    )


@app.route("/products")
@login_required
def products():
    page      = request.args.get("page", 1, type=int)
    search    = request.args.get("q", "").strip()
    category  = request.args.get("category", "").strip()
    min_price = request.args.get("min_price", "").strip()
    max_price = request.args.get("max_price", "").strip()
    low_stock = request.args.get("low_stock")
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
        products=items,
        page=page,
        total_pages=total_pages,
        search=search,
        categories=categories,
        category=category,
        min_price=min_price,
        max_price=max_price,
        low_stock=low_stock,
        sort=sort
    )


@app.route("/add-product", methods=["GET", "POST"])
@login_required
def add_product_route():
    if request.method == "POST":
        f = request.form
        name     = f.get("name", "").strip()
        category = f.get("category", "").strip()
        unit     = f.get("unit", "").strip()
        if not name or not category or not unit:
            flash("Name, category and unit are required.", "error")
            return render_template("add_product.html")
        try:
            add_product(
                name=name, category=category, unit=unit,
                net_weight=float(f.get("net_weight") or 0),
                quantity=float(f.get("quantity") or 0),
                purchase_price=float(f.get("purchase_price") or 0),
                selling_price=float(f.get("selling_price") or 0),
                min_stock=int(f.get("min_stock") or 5)
            )
        except (ValueError, TypeError):
            flash("Please enter valid numbers for price, quantity, and weight.", "error")
            return render_template("add_product.html")
        flash(f'"{name}" added to inventory.', "success")
        return redirect(url_for("products"))
    return render_template("add_product.html")


@app.route("/edit-product/<int:id>", methods=["GET", "POST"])
@login_required
def edit_product(id):
    product = get_product_by_id(id)
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("products"))
    if request.method == "POST":
        f = request.form
        name      = f.get("name", "").strip()
        category  = f.get("category", "").strip()
        unit_type = f.get("unit_type", "").strip()
        if not name or not category or not unit_type:
            flash("Name, category and unit are required.", "error")
            return render_template("edit_product.html", product=product)
        try:
            update_product(
                product_id=id, name=name, category=category,
                unit_type=unit_type,
                quantity=float(f.get("quantity") or 0),
                min_stock=int(f.get("min_stock") or 5),
                purchase_price=float(f.get("purchase_price") or 0),
                selling_price=float(f.get("selling_price") or 0)
            )
        except (ValueError, TypeError):
            flash("Please enter valid numbers for price and quantity.", "error")
            return render_template("edit_product.html", product=product)
        flash(f'"{name}" updated successfully.', "success")
        return redirect(url_for("products"))
    return render_template("edit_product.html", product=product)


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
        if qty > float(product["quantity"]):
            flash(f'Not enough stock. Only {product["quantity"]} available.', "error")
            return redirect(url_for("sell_product"))

        amount = qty * float(product["selling_price"])
        profit = qty * (float(product["selling_price"]) - float(product["purchase_price"]))

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

    return render_template("sell.html", products=get_all_products())


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


# endpoint aliases so url_for('add_product') and url_for('delete_product') work in templates
app.add_url_rule("/add-product",          endpoint="add_product",
                 view_func=add_product_route, methods=["GET", "POST"])
app.add_url_rule("/delete-product/<int:id>", endpoint="delete_product",
                 view_func=delete_product_route, methods=["POST"])


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "true").lower() == "true")
