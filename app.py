from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

app = Flask(__name__)
app.secret_key = "secret123"

# ---------------- DATABASE ----------------
def get_db():
    return sqlite3.connect("database.db")

def init_db():
    conn = get_db()
    c = conn.cursor()

    # USERS
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        password TEXT,
        role TEXT,
        status TEXT,
        shop_name TEXT
    )""")

    # PRODUCTS
    c.execute("""CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        price INTEGER,
        stock INTEGER,
        shop_name TEXT
    )""")

    # SALES
    c.execute("""CREATE TABLE IF NOT EXISTS sales(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_name TEXT,
        total INTEGER
    )""")

    # SALE ITEMS
    c.execute("""CREATE TABLE IF NOT EXISTS sale_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_id INTEGER,
        product_name TEXT,
        price INTEGER,
        qty INTEGER,
        total INTEGER
    )""")

    conn.commit()
    conn.close()

init_db()

# ---------------- LOGIN ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        # ADMIN LOGIN
        if email == "admin@gmail.com" and password == "admin123":
            session["role"] = "admin"
            session["email"] = email
            return redirect("/admin")

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email=? AND password=?", (email, password))
        user = c.fetchone()

        if user:
            if user[4] != "approved":
                return "Wait for admin approval"
            session["role"] = "shop"
            session["shop"] = user[5]
            session["email"] = user[1]
            return redirect("/dashboard")

        return "Invalid Login"

    return render_template("login.html")

# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO users(email,password,role,status,shop_name) VALUES(?,?,?,?,?)",
                  (request.form["email"], request.form["password"], "shop", "pending", request.form["shop"]))
        conn.commit()
        conn.close()
        return "Registered! Wait for admin approval"

    return render_template("register.html")

# ---------------- CHANGE PASSWORD ----------------
@app.route("/change_password", methods=["GET", "POST"])
def change_password():
    if session.get("role") not in ["shop", "admin"]:
        return "Unauthorized"

    if request.method == "POST":
        old_password = request.form.get("old_password", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not old_password or not new_password:
            return "Enter old and new password."
        if new_password != confirm_password:
            return "New passwords do not match."

        if session.get("role") == "admin":
            if old_password != "admin123":
                return "Old password is incorrect."
            # admin password is hardcoded in this simple app
            # no DB update required
            return "Admin password changed in memory only (hardcoded environment)."

        email = session.get("email")
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT password FROM users WHERE email=?", (email,))
        row = c.fetchone()
        if not row or row[0] != old_password:
            conn.close()
            return "Old password is incorrect."

        c.execute("UPDATE users SET password=? WHERE email=?", (new_password, email))
        conn.commit()
        conn.close()
        return "Password updated successfully."

    return render_template("change_password.html")

# ---------------- ADMIN ----------------
@app.route("/admin")
def admin():
    if session.get("role") != "admin":
        return "Unauthorized"

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE role='shop'")
    users = c.fetchall()

    return render_template("admin.html", users=users)

@app.route("/approve/<int:id>")
def approve(id):
    if session.get("role") != "admin":
        return "Unauthorized"

    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET status='approved' WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/admin")

# ---------------- SHOP DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if session.get("role") not in ["shop", "admin"]:
        return "Unauthorized"

    role = session.get("role")
    return render_template("dashboard.html", role=role)

# ---------------- ADD PRODUCT ----------------
@app.route("/add_product", methods=["POST"])
def add_product():
    if session.get("role") not in ["shop", "admin"]:
        return "Unauthorized"

    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO products(name,price,stock,shop_name) VALUES(?,?,?,?)",
              (request.form["name"], request.form["price"], request.form["stock"], session["shop"]))
    conn.commit()
    conn.close()

    return redirect("/dashboard")

# ---------------- BILLING PAGE ----------------
@app.route("/billing")
def billing():
    if session.get("role") not in ["shop", "admin"]:
        return "Unauthorized"

    role = session.get("role")
    if role == "admin":
        return render_template("billing.html", products=[], shop=session.get("shop"), role=role, info="Billing is available for shop users only. Please log in as a shop user.")

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE shop_name=?", (session["shop"],))
    products = c.fetchall()

    return render_template("billing.html", products=products, shop=session.get("shop"), role=role, info="")

# ---------------- GENERATE BILL ----------------
@app.route("/generate_bill", methods=["POST"])
def generate_bill():
    if session.get("role") != "shop":
        return "Billing is available for shop users only."

    customer_name = request.form.get("customer_name", "").strip()
    customer_email = request.form.get("customer_email", "").strip()
    customer_phone = request.form.get("customer_phone", "").strip()

    if not customer_name or not customer_email:
        return "Please provide customer name and email before billing."

    product_ids = request.form.getlist("product_id")
    quantities = request.form.getlist("qty")

    conn = get_db()
    c = conn.cursor()

    total_bill = 0
    items = []

    for i in range(len(product_ids)):
        pid = product_ids[i]
        qty = int(quantities[i])

        if qty <= 0:
            continue

        c.execute("SELECT name, price, stock FROM products WHERE id=? AND shop_name=?",
                  (pid, session["shop"]))
        product = c.fetchone()

        if not product:
            continue

        name, price, stock = product

        if qty > stock:
            return f"Not enough stock for {name}"

        item_total = price * qty
        total_bill += item_total

        c.execute("UPDATE products SET stock=? WHERE id=?", (stock - qty, pid))

        items.append((name, price, qty, item_total))

    if not items:
        return "No products selected for billing."

    # SAVE SALE
    c.execute("INSERT INTO sales(shop_name,total) VALUES(?,?)",
              (session["shop"], total_bill))
    sale_id = c.lastrowid

    for item in items:
        c.execute("""INSERT INTO sale_items(sale_id,product_name,price,qty,total)
                     VALUES(?,?,?,?,?)""",
                  (sale_id, item[0], item[1], item[2], item[3]))

    conn.commit()
    conn.close()

    # ---------------- PDF ----------------
    pdf_file = f"invoice_{sale_id}.pdf"
    doc = SimpleDocTemplate(pdf_file)
    styles = getSampleStyleSheet()

    content = []
    content.append(Paragraph(f"Invoice ID: {sale_id}", styles["Normal"]))
    content.append(Paragraph(f"Shop: {session['shop']}", styles["Normal"]))
    content.append(Paragraph(f"Customer: {customer_name}", styles["Normal"]))
    content.append(Paragraph(f"Customer Email: {customer_email}", styles["Normal"]))
    if customer_phone:
        content.append(Paragraph(f"Customer Phone: {customer_phone}", styles["Normal"]))

    for item in items:
        content.append(Paragraph(f"{item[0]} x {item[2]} = ₹{item[3]}", styles["Normal"]))

    content.append(Paragraph(f"Total: ₹{total_bill}", styles["Normal"]))

    doc.build(content)

    return f"Bill Created! <a href='/{pdf_file}'>Download PDF</a>"

# ---------------- SALES HISTORY ----------------
@app.route("/sales")
def sales():
    if session.get("role") not in ["shop", "admin"]:
        return "Unauthorized"

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM sales WHERE shop_name=?", (session["shop"],))
    data = c.fetchall()
    conn.close()

    return render_template("sales.html", sales=data)

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)