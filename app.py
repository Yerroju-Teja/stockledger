import math
import os
from functools import wraps

from flask import (Flask, flash, redirect, render_template,
                   request, session, url_for, send_from_directory)
from werkzeug.security import check_password_hash, generate_password_hash

from db import (
    add_product, delete_product, get_all_products,
    get_dashboard_stats, get_low_stock_alerts,
    get_product_by_id, get_products_filtered,
    get_sales_report_data, get_today_sales_profit,
    get_user_by_username, create_user, record_sale, update_product,
    record_multiple_sales
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

@app.route("/")
def landing():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")




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
            session["user_id"] = user["id"]
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
        create_user(username, generate_password_hash(password))
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
    user_id = session["user_id"]
    stats = get_dashboard_stats(user_id)
    alerts = get_low_stock_alerts(user_id)
    today = get_today_sales_profit(user_id)

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
    user_id=session["user_id"],
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
    user_id = session["user_id"]
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
                user_id=user_id,
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
    product = get_product_by_id(id, session["user_id"])
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
                user_id=session["user_id"],
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
    product = get_product_by_id(id, session["user_id"])
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("products"))
    delete_product(id, session["user_id"])
    flash(f'"{product["name"]}" deleted.', "success")
    return redirect(url_for("products"))


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell_product():
    if request.method == "POST":
        if request.is_json:
            cart = request.json
            if not cart:
                return {"success": False, "error": "Cart is empty."}, 400
            
            try:
                formatted_cart = []
                total_amount = 0
                for item in cart:
                    product = get_product_by_id(int(item["product_id"]), session["user_id"])
                    if not product:
                        return {"success": False, "error": "A product was not found."}, 404
                    
                    qty = float(item["quantity"])
                    if qty <= 0:
                        return {"success": False, "error": "Invalid quantity."}, 400
                    if qty > float(product["quantity"]):
                        return {"success": False, "error": f"Not enough stock for {product['name']}."}, 400
                        
                    amount = qty * float(product["selling_price"])
                    profit = qty * (float(product["selling_price"]) - float(product["purchase_price"]))
                    total_amount += amount
                    
                    formatted_cart.append({
                        "product_id": product["id"],
                        "quantity": qty,
                        "amount": round(amount, 2),
                        "profit": round(profit, 2)
                    })
                
                success = record_multiple_sales(session["user_id"], formatted_cart)
                if success:
                    flash(f'Sale completed successfully! Total: ₹{total_amount:.2f}', "success")
                    return {"success": True, "redirect": url_for("dashboard")}
                else:
                    return {"success": False, "error": "Sale failed due to a stock conflict. Please refresh and try again."}, 409
            except Exception as e:
                return {"success": False, "error": "An error occurred during processing."}, 500
        else:
            flash("Invalid request format.", "error")
            return redirect(url_for("sell_product"))

    return render_template("sell.html", products=get_all_products(session["user_id"]))


@app.route("/sales-report")
@login_required
def sales_report():
    date_from = request.args.get("date_from", "").strip() or None
    date_to   = request.args.get("date_to",   "").strip() or None

    stats, sales, chart_daily, chart_top = get_sales_report_data(
        user_id=session["user_id"],
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


# ───────────────── ERROR HANDLERS ─────────────────

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template("404.html"), 500


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "true").lower() == "true")
