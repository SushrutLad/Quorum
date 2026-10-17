"""EUMS - Energy & Utility Management System.

Start the app with:  python app.py   (then open http://127.0.0.1:5000)
"""
import os
from datetime import datetime

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

import db


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY="dev-only-key", DATABASE=os.path.join(app.root_path, "eums.db"))
    app.config.from_pyfile("config.py", silent=True)       # local settings, if present
    if test_config:
        app.config.update(test_config)
    app.config["DATABASE"] = os.path.join(app.root_path, app.config["DATABASE"])   # relative paths -> this folder

    app.teardown_appcontext(db.close_db)

    import routes_customer
    import routes_staff
    app.register_blueprint(routes_staff.bp)
    app.register_blueprint(routes_customer.bp)

    register_helpers(app)

    @app.route("/")
    def index():
        if "user_id" not in session:
            return redirect(url_for("login"))
        return redirect(home_for(session["role"]))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form["username"].strip().lower()
            user = db.query("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,), one=True)
            if user and check_password_hash(user["password_hash"], request.form["password"]):
                session.clear()
                session.update(user_id=user["user_id"], role=user["role"], name=user["full_name"])
                return redirect(home_for(user["role"]))
            flash("Invalid username or password.", "error")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403, message="You are not allowed to see this page."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404, message="Page not found."), 404

    return app


def home_for(role):
    return url_for("customer.dashboard") if role == "customer" else url_for("staff.dashboard")


def register_helpers(app):
    @app.template_filter("money")
    def money(value):
        return f"₹{value or 0:,.2f}"

    @app.template_filter("nice_date")
    def nice_date(value):
        if not value:
            return "-"
        fmt = "%Y-%m-%d %H:%M" if len(value) > 10 else "%Y-%m-%d"
        out = datetime.strptime(value[:16], fmt)
        return out.strftime("%d %b %Y, %H:%M" if len(value) > 10 else "%d %b %Y")

    @app.template_filter("month_name")
    def month_name(value):
        return datetime.strptime(value, "%Y-%m").strftime("%b %Y")

    @app.template_filter("label")
    def label(value):
        return (value or "").replace("_", " ").title()

    @app.template_filter("method_name")
    def method_name(value):
        return {"card": "Card", "upi": "UPI", "netbanking": "Net Banking", "wallet": "Wallet", "cash": "Cash"}.get(value, value)

    @app.context_processor
    def unread_count():
        if session.get("user_id"):
            n = db.query("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0",
                         (session["user_id"],), one=True)[0]
            return {"unread": n}
        return {"unread": 0}


if __name__ == "__main__":
    create_app().run(debug=True)
