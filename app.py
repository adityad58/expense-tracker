from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import functools

app = Flask(__name__, 
            template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
            static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.secret_key = "spendly-secret-key-change-in-production"

# Database path — Railway pe /tmp mein store hoga
DB_PATH = os.path.join('/tmp', 'expenses.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL,
            email      TEXT    NOT NULL UNIQUE,
            password   TEXT    NOT NULL,
            created_at TEXT    DEFAULT (datetime('now'))
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            title       TEXT    NOT NULL,
            amount      REAL    NOT NULL,
            category    TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            description TEXT,
            created_at  TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()

with app.app_context():
    init_db()

def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Pehle login karo!", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or not password:
            return render_template("register.html", error="Saare fields bharo!")
        if len(password) < 8:
            return render_template("register.html", error="Password kam se kam 8 characters ka hona chahiye!")
        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            db.close()
            return render_template("register.html", error="Yeh email pehle se registered hai!")
        hashed_pw = generate_password_hash(password)
        db.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                   (name, email, hashed_pw))
        db.commit()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        db.close()
        session["user_id"]   = user["id"]
        session["user_name"] = user["name"]
        flash("Account ban gaya! Welcome to Spendly 🎉", "success")
        return redirect(url_for("dashboard"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        db   = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        db.close()
        if not user or not check_password_hash(user["password"], password):
            return render_template("login.html", error="Email ya password galat hai!")
        session["user_id"]   = user["id"]
        session["user_name"] = user["name"]
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("Successfully logout ho gaye!", "success")
    return redirect(url_for("landing"))

@app.route("/dashboard")
@login_required
def dashboard():
    db      = get_db()
    user_id = session["user_id"]
    category  = request.args.get("category", "")
    date_from = request.args.get("date_from", "")
    date_to   = request.args.get("date_to", "")
    query  = "SELECT * FROM expenses WHERE user_id = ?"
    params = [user_id]
    if category:
        query  += " AND category = ?"
        params.append(category)
    if date_from:
        query  += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query  += " AND date <= ?"
        params.append(date_to)
    query += " ORDER BY date DESC"
    expenses = db.execute(query, params).fetchall()
    total = sum(e["amount"] for e in expenses)
    cat_totals = {}
    for e in expenses:
        cat_totals[e["category"]] = cat_totals.get(e["category"], 0) + e["amount"]
    db.close()
    return render_template("dashboard.html", expenses=expenses, total=total,
                           cat_totals=cat_totals,
                           filters={"category": category, "date_from": date_from, "date_to": date_to})

@app.route("/profile")
@login_required
def profile():
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    stats = db.execute(
        "SELECT COUNT(*) as count, COALESCE(SUM(amount),0) as total FROM expenses WHERE user_id = ?",
        (session["user_id"],)).fetchone()
    db.close()
    return render_template("profile.html", user=user, stats=stats)

CATEGORIES = ["Food", "Bills", "Transport", "Health", "Shopping", "Entertainment", "Education", "Other"]

@app.route("/expenses/add", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "POST":
        title       = request.form.get("title", "").strip()
        amount      = request.form.get("amount", "")
        category    = request.form.get("category", "")
        date        = request.form.get("date", "")
        description = request.form.get("description", "").strip()
        if not title or not amount or not category or not date:
            return render_template("add_expense.html", categories=CATEGORIES, error="Saare zaroori fields bharo!")
        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError
        except ValueError:
            return render_template("add_expense.html", categories=CATEGORIES, error="Amount sahi number hona chahiye!")
        db = get_db()
        db.execute("INSERT INTO expenses (user_id, title, amount, category, date, description) VALUES (?, ?, ?, ?, ?, ?)",
                   (session["user_id"], title, amount, category, date, description))
        db.commit()
        db.close()
        flash("Expense add ho gaya! ✅", "success")
        return redirect(url_for("dashboard"))
    return render_template("add_expense.html", categories=CATEGORIES)

@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_expense(id):
    db      = get_db()
    expense = db.execute("SELECT * FROM expenses WHERE id = ? AND user_id = ?",
                         (id, session["user_id"])).fetchone()
    if not expense:
        db.close()
        flash("Expense nahi mila!", "error")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        title       = request.form.get("title", "").strip()
        amount      = request.form.get("amount", "")
        category    = request.form.get("category", "")
        date        = request.form.get("date", "")
        description = request.form.get("description", "").strip()
        try:
            amount = float(amount)
        except ValueError:
            return render_template("edit_expense.html", expense=expense, categories=CATEGORIES, error="Amount sahi number hona chahiye!")
        db.execute("UPDATE expenses SET title=?, amount=?, category=?, date=?, description=? WHERE id=? AND user_id=?",
                   (title, amount, category, date, description, id, session["user_id"]))
        db.commit()
        db.close()
        flash("Expense update ho gaya! ✏️", "success")
        return redirect(url_for("dashboard"))
    db.close()
    return render_template("edit_expense.html", expense=expense, categories=CATEGORIES)

@app.route("/expenses/<int:id>/delete", methods=["POST"])
@login_required
def delete_expense(id):
    db = get_db()
    db.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (id, session["user_id"]))
    db.commit()
    db.close()
    flash("Expense delete ho gaya! 🗑️", "success")
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, host="0.0.0.0", port=port)
