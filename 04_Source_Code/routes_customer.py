"""Customer self-service portal. Every query is filtered by the logged-in customer."""

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from auth import login_required
from db import get_db, query
from routes_staff import load_bill, record_payment

bp = Blueprint("customer", __name__, url_prefix="/my")

PAY_METHODS = {"card": "Credit / Debit Card", "upi": "UPI (GPay, PhonePe, etc.)",
               "netbanking": "Net Banking", "wallet": "Wallet (Paytm, etc.)"}


def me():
    """The customers row for the logged-in user."""
    return query("SELECT * FROM customers WHERE user_id = ?", (session["user_id"],), one=True) or abort(403)


def own_bill(bill_id, customer_id):
    """Load a bill only if it belongs to this customer, otherwise 403."""
    data = load_bill(bill_id)
    if data["bill"]["customer_id"] != customer_id:
        abort(403)
    return data


@bp.route("/dashboard")
@login_required("customer")
def dashboard():
    c = me()
    cards = query("""SELECT c.connection_id, c.connection_no, c.status, u.name AS utility, u.unit,
                            (SELECT bill_id FROM bills b WHERE b.connection_id = c.connection_id
                              ORDER BY bill_date DESC, bill_id DESC LIMIT 1) AS last_bill_id
                       FROM connections c JOIN utilities u ON u.utility_id = c.utility_id
                      WHERE c.customer_id = ? ORDER BY u.utility_id""", (c["customer_id"],))
    latest = {r["bill_id"]: r for r in query("SELECT * FROM v_bill_summary WHERE customer_id = ?", (c["customer_id"],))}
    cards = [dict(card) | {"bill": latest.get(card["last_bill_id"])} for card in cards]

    rows = query("""SELECT billing_month, utility, total_amount FROM v_bill_summary
                     WHERE customer_id = ? ORDER BY billing_month""", (c["customer_id"],))
    months = sorted({r["billing_month"] for r in rows})[-6:]
    series = {}
    for r in rows:
        if r["billing_month"] in months:
            series.setdefault(r["utility"], {m: 0 for m in months})[r["billing_month"]] = r["total_amount"]
    chart = {"months": months, "series": {u: list(v.values()) for u, v in series.items()}}

    recent = query("SELECT * FROM v_bill_summary WHERE customer_id = ? ORDER BY bill_date DESC, bill_id DESC LIMIT 5",
                   (c["customer_id"],))
    due = query("SELECT COALESCE(SUM(outstanding), 0) FROM v_bill_summary WHERE customer_id = ? AND status <> 'paid'",
                (c["customer_id"],), one=True)[0]
    return render_template("portal/dashboard.html", c=c, cards=cards, chart=chart, recent=recent, due=due)


@bp.route("/connections")
@login_required("customer")
def connections():
    rows = query("""SELECT c.*, u.name AS utility, u.unit, t.name AS tariff, m.meter_no,
                           (SELECT MAX(reading_value) FROM meter_readings mr WHERE mr.meter_id = m.meter_id) AS last_value,
                           (SELECT MAX(reading_date) FROM meter_readings mr WHERE mr.meter_id = m.meter_id) AS last_date
                      FROM connections c
                      JOIN utilities u ON u.utility_id = c.utility_id
                      JOIN tariff_plans t ON t.tariff_id = c.tariff_id
                      LEFT JOIN meters m ON m.connection_id = c.connection_id AND m.status = 'active'
                     WHERE c.customer_id = ? ORDER BY u.utility_id""", (me()["customer_id"],))
    return render_template("portal/connections.html", connections=rows)


@bp.route("/bills")
@login_required("customer")
def bills():
    rows = query("SELECT * FROM v_bill_summary WHERE customer_id = ? ORDER BY bill_date DESC, bill_id DESC",
                 (me()["customer_id"],))
    return render_template("portal/bills.html", bills=rows)


@bp.route("/bills/<int:bill_id>")
@login_required("customer")
def bill_detail(bill_id):
    return render_template("bill_detail.html", **own_bill(bill_id, me()["customer_id"]), back=url_for("customer.bills"))


@bp.route("/bills/<int:bill_id>/pay", methods=["GET", "POST"])
@login_required("customer")
def pay(bill_id):
    data = own_bill(bill_id, me()["customer_id"])
    bill = data["bill"]
    if bill["status"] == "paid":
        flash("This bill is already paid.", "info")
        return redirect(url_for("customer.bill_detail", bill_id=bill_id))
    if request.method == "POST":
        method = request.form.get("method")
        if method not in PAY_METHODS:
            flash("Please choose a payment method.", "error")
            return render_template("portal/pay.html", bill=bill, methods=PAY_METHODS)
        try:
            amount = float(request.form.get("amount") or bill["outstanding"])
        except ValueError:
            amount = 0
        # Payment gateway is simulated for the mid-semester build: the payment always succeeds.
        receipt, error = record_payment(bill_id, amount, method, session["user_id"])
        if error:
            flash(error, "error")
            return render_template("portal/pay.html", bill=bill, methods=PAY_METHODS)
        flash(f"Payment successful. Receipt number {receipt}.", "success")
        return redirect(url_for("customer.bill_detail", bill_id=bill_id))
    return render_template("portal/pay.html", bill=bill, methods=PAY_METHODS)


@bp.route("/usage")
@login_required("customer")
def usage():
    rows = query("""SELECT mr.reading_date, mr.previous_value, mr.reading_value, mr.consumption,
                           u.name AS utility, u.unit, m.meter_no
                      FROM meter_readings mr
                      JOIN meters m ON m.meter_id = mr.meter_id
                      JOIN connections c ON c.connection_id = m.connection_id
                      JOIN utilities u ON u.utility_id = c.utility_id
                     WHERE c.customer_id = ? ORDER BY u.utility_id, mr.reading_date""", (me()["customer_id"],))
    # One small chart per utility, because kWh, kL and SCM cannot share an axis.
    charts = {}
    for r in rows:
        ch = charts.setdefault(r["utility"], {"unit": r["unit"], "labels": [], "values": []})
        ch["labels"].append(r["reading_date"][:7])
        ch["values"].append(r["consumption"])
    return render_template("portal/usage.html", rows=list(reversed(rows)), charts=charts)


@bp.route("/complaints", methods=["GET", "POST"])
@login_required("customer")
def complaints():
    c = me()
    if request.method == "POST":
        f = request.form
        if not f.get("issue", "").strip():
            flash("Please describe the issue.", "error")
            return redirect(url_for("customer.complaints"))
        conn = query("SELECT connection_id FROM connections WHERE connection_id = ? AND customer_id = ?",
                     (f.get("connection_id"), c["customer_id"]), one=True)
        db = get_db()
        next_no = query("SELECT COALESCE(MAX(complaint_id), 0) + 4501 FROM complaints", one=True)[0]
        db.execute("""INSERT INTO complaints (complaint_no, customer_id, connection_id, issue, description, priority)
                      VALUES (?, ?, ?, ?, ?, ?)""",
                   (f"CMP{next_no}", c["customer_id"], conn["connection_id"] if conn else None,
                    f["issue"].strip(), f.get("description", "").strip() or None, f.get("priority", "medium")))
        db.execute("INSERT INTO audit_log (action, details) VALUES (?, ?)",
                   ("New complaint submitted", f"{f['issue'].strip()} - #CMP{next_no}"))
        db.commit()
        flash(f"Complaint CMP{next_no} registered. We will update you here.", "success")
        return redirect(url_for("customer.complaints"))
    rows = query("""SELECT cp.*, u.name AS utility FROM complaints cp
                      LEFT JOIN connections c ON c.connection_id = cp.connection_id
                      LEFT JOIN utilities u ON u.utility_id = c.utility_id
                     WHERE cp.customer_id = ? ORDER BY cp.complaint_id DESC""", (c["customer_id"],))
    conns = query("""SELECT c.connection_id, c.connection_no, u.name AS utility FROM connections c
                       JOIN utilities u ON u.utility_id = c.utility_id WHERE c.customer_id = ?""", (c["customer_id"],))
    return render_template("portal/complaints.html", complaints=rows, connections=conns)


@bp.route("/outages")
@login_required("customer")
def outages():
    c = me()
    rows = query("""SELECT o.*, u.name AS utility FROM outages o
                      JOIN utilities u ON u.utility_id = o.utility_id
                     WHERE o.area = ? AND o.utility_id IN (SELECT utility_id FROM connections WHERE customer_id = ?)
                     ORDER BY CASE o.status WHEN 'active' THEN 1 WHEN 'scheduled' THEN 2 ELSE 3 END, o.start_time DESC""",
                 (c["area"], c["customer_id"]))
    return render_template("portal/outages.html", outages=rows, area=c["area"])


@bp.route("/profile", methods=["GET", "POST"])
@login_required("customer")
def profile():
    c = me()
    if request.method == "POST":
        f = request.form
        db = get_db()
        if f.get("action") == "password":
            user = query("SELECT password_hash FROM users WHERE user_id = ?", (session["user_id"],), one=True)
            if not check_password_hash(user["password_hash"], f["current"]):
                flash("Current password is wrong.", "error")
            elif len(f["new"]) < 6:
                flash("New password must be at least 6 characters.", "error")
            else:
                db.execute("UPDATE users SET password_hash = ? WHERE user_id = ?",
                           (generate_password_hash(f["new"]), session["user_id"]))
                db.commit()
                flash("Password changed.", "success")
        else:
            if not f["phone"].isdigit() or len(f["phone"]) != 10:
                flash("Phone number must be 10 digits.", "error")
            else:
                db.execute("UPDATE customers SET phone = ?, address = ? WHERE customer_id = ?",
                           (f["phone"], f["address"].strip(), c["customer_id"]))
                db.commit()
                flash("Profile updated.", "success")
        return redirect(url_for("customer.profile"))
    return render_template("portal/profile.html", c=c)


@bp.route("/notifications", methods=["GET", "POST"])
@login_required("customer")
def notifications():
    db = get_db()
    if request.method == "POST":
        db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (session["user_id"],))
        db.commit()
        return redirect(url_for("customer.notifications"))
    rows = query("SELECT * FROM notifications WHERE user_id = ? ORDER BY notification_id DESC LIMIT 50",
                 (session["user_id"],))
    return render_template("portal/notifications.html", notifications=rows)
