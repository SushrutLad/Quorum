"""Pages used by staff: admin and employees (meter readers, billing officers, technicians)."""
import sqlite3
from datetime import date, datetime

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from auth import login_required
from billing import generate_bill
from db import get_db, query

bp = Blueprint("staff", __name__, url_prefix="/staff")

STAFF = ("admin", "employee")


def log(action, details):
    get_db().execute("INSERT INTO audit_log (action, details) VALUES (?, ?)", (action, details))


def last_months(n):
    """The last n billing months, oldest first, e.g. ['2025-10', ..., '2026-03']."""
    rows = query("SELECT DISTINCT billing_month FROM bills ORDER BY billing_month DESC LIMIT ?", (n,))
    return [r[0] for r in reversed(rows)]


# ------------------------------------------------------------------ dashboard
@bp.route("/dashboard")
@login_required(*STAFF)
def dashboard():
    months = last_months(6)
    current = months[-1] if months else date.today().strftime("%Y-%m")
    previous = months[-2] if len(months) > 1 else current

    kpi = {
        "customers": query("SELECT COUNT(*) FROM customers", one=True)[0],
        "connections": query("SELECT COUNT(*) FROM connections WHERE status = 'active'", one=True)[0],
        "collected": query("SELECT COALESCE(SUM(amount), 0) FROM payments", one=True)[0],
        "pending_amount": query("SELECT COALESCE(SUM(outstanding), 0) FROM v_bill_summary WHERE status <> 'paid'", one=True)[0],
        "pending_bills": query("SELECT COUNT(*) FROM bills WHERE status <> 'paid'", one=True)[0],
        "open_complaints": query("SELECT COUNT(*) FROM complaints WHERE status <> 'resolved'", one=True)[0],
        "high_priority": query("SELECT COUNT(*) FROM complaints WHERE status <> 'resolved' AND priority = 'high'", one=True)[0],
        "active_outages": query("SELECT COUNT(*) FROM outages WHERE status = 'active'", one=True)[0],
        "billed_now": query("SELECT COALESCE(SUM(total_amount), 0) FROM bills WHERE billing_month = ?", (current,), one=True)[0],
        "billed_before": query("SELECT COALESCE(SUM(total_amount), 0) FROM bills WHERE billing_month = ?", (previous,), one=True)[0],
    }
    kpi["affected"] = query(
        """SELECT COUNT(DISTINCT cu.customer_id) FROM outages o
             JOIN customers cu ON cu.area = o.area
             JOIN connections c ON c.customer_id = cu.customer_id AND c.utility_id = o.utility_id
            WHERE o.status = 'active'""", one=True)[0]

    # Billed amount per utility per month (all in rupees, so one axis is fine)
    rows = query("SELECT billing_month, utility, total_billed FROM v_monthly_consumption WHERE billing_month >= ?",
                 (months[0] if months else current,))
    series = {}
    for r in rows:
        series.setdefault(r["utility"], {m: 0 for m in months})[r["billing_month"]] = r["total_billed"]
    chart = {"months": months, "series": {u: list(v.values()) for u, v in series.items()}}

    split = query("""SELECT u.name AS utility, COALESCE(SUM(p.amount), 0) AS amount
                       FROM utilities u
                       LEFT JOIN connections c ON c.utility_id = u.utility_id
                       LEFT JOIN bills b ON b.connection_id = c.connection_id
                       LEFT JOIN payments p ON p.bill_id = b.bill_id
                      GROUP BY u.utility_id ORDER BY u.utility_id""")
    activity = query("SELECT * FROM audit_log ORDER BY log_id DESC LIMIT 6")
    return render_template("staff/dashboard.html", kpi=kpi, chart=chart, current=current,
                           split=[dict(r) for r in split], activity=activity)


# ------------------------------------------------------------------ customers
@bp.route("/customers")
@login_required(*STAFF)
def customers():
    q = request.args.get("q", "").strip()
    like = f"%{q}%"
    rows = query("""SELECT cu.*, COUNT(c.connection_id) AS n_connections
                      FROM customers cu LEFT JOIN connections c ON c.customer_id = cu.customer_id
                     WHERE cu.full_name LIKE ? OR cu.customer_code LIKE ? OR cu.area LIKE ? OR cu.phone LIKE ?
                     GROUP BY cu.customer_id ORDER BY cu.customer_id DESC""", (like, like, like, like))
    return render_template("staff/customers.html", customers=rows, q=q)


@bp.route("/customers/new", methods=["GET", "POST"])
@login_required(*STAFF)
def customer_new():
    if request.method == "POST":
        f = request.form
        email = f["email"].strip().lower()
        if not f["phone"].isdigit() or len(f["phone"]) != 10:
            flash("Phone number must be 10 digits.", "error")
            return render_template("staff/customer_form.html", form=f)
        db = get_db()
        try:
            cur = db.execute("INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, 'customer', ?)",
                             (email, generate_password_hash(f["password"]), f["full_name"].strip()))
            next_no = query("SELECT COALESCE(MAX(customer_id), 0) + 1001 FROM customers", one=True)[0]
            db.execute("""INSERT INTO customers (user_id, customer_code, full_name, phone, email, address, area, category)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                       (cur.lastrowid, f"C{next_no}", f["full_name"].strip(), f["phone"], email,
                        f["address"].strip(), f["area"], f["category"]))
            log("New customer registered", f["full_name"].strip())
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            flash("A customer with this email already exists.", "error")
            return render_template("staff/customer_form.html", form=f)
        flash(f"Customer C{next_no} created. They can log in with {email}.", "success")
        return redirect(url_for("staff.customers"))
    return render_template("staff/customer_form.html", form={})


@bp.route("/customers/<int:customer_id>")
@login_required(*STAFF)
def customer_detail(customer_id):
    customer = query("SELECT * FROM customers WHERE customer_id = ?", (customer_id,), one=True) or abort(404)
    connections = query("""SELECT c.*, u.name AS utility, m.meter_no FROM connections c
                             JOIN utilities u ON u.utility_id = c.utility_id
                             LEFT JOIN meters m ON m.connection_id = c.connection_id AND m.status = 'active'
                            WHERE c.customer_id = ?""", (customer_id,))
    bills = query("SELECT * FROM v_bill_summary WHERE customer_id = ? ORDER BY bill_date DESC LIMIT 12", (customer_id,))
    return render_template("staff/customer_detail.html", customer=customer, connections=connections, bills=bills)


# ------------------------------------------------------------------ connections
@bp.route("/connections")
@login_required(*STAFF)
def connections():
    utility = request.args.get("utility", "")
    rows = query("""SELECT c.*, u.name AS utility, cu.full_name, cu.customer_code, cu.area, m.meter_no, t.name AS tariff
                      FROM connections c
                      JOIN utilities u ON u.utility_id = c.utility_id
                      JOIN customers cu ON cu.customer_id = c.customer_id
                      JOIN tariff_plans t ON t.tariff_id = c.tariff_id
                      LEFT JOIN meters m ON m.connection_id = c.connection_id AND m.status = 'active'
                     WHERE (? = '' OR u.name = ?)
                     ORDER BY c.connection_id DESC""", (utility, utility))
    return render_template("staff/connections.html", connections=rows, utility=utility)


@bp.route("/connections/new", methods=["GET", "POST"])
@login_required(*STAFF)
def connection_new():
    customers = query("SELECT customer_id, customer_code, full_name, category FROM customers ORDER BY full_name")
    utilities = query("SELECT * FROM utilities ORDER BY utility_id")
    if request.method == "POST":
        f = request.form
        customer = query("SELECT * FROM customers WHERE customer_id = ?", (f["customer_id"],), one=True) or abort(400)
        utility = query("SELECT * FROM utilities WHERE utility_id = ?", (f["utility_id"],), one=True) or abort(400)
        tariff = query("SELECT tariff_id FROM tariff_plans WHERE utility_id = ? AND category = ?",
                       (utility["utility_id"], customer["category"]), one=True)
        db = get_db()
        try:
            next_no = query("SELECT COALESCE(MAX(connection_id), 0) + 1001 FROM connections", one=True)[0]
            prefix = utility["name"][:4].upper()
            today = date.today().isoformat()
            cur = db.execute("""INSERT INTO connections (connection_no, customer_id, utility_id, tariff_id, installed_on)
                                VALUES (?, ?, ?, ?, ?)""",
                             (f"{prefix}{next_no}", customer["customer_id"], utility["utility_id"], tariff["tariff_id"], today))
            db.execute("INSERT INTO meters (meter_no, connection_id, initial_reading, installed_on) VALUES (?, ?, ?, ?)",
                       (f"MTR-{prefix[0]}-{next_no}", cur.lastrowid, float(f.get("initial_reading") or 0), today))
            log("New connection", f"{prefix}{next_no} for {customer['full_name']}")
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            flash(f"{customer['full_name']} already has a {utility['name']} connection.", "error")
            return render_template("staff/connection_form.html", customers=customers, utilities=utilities)
        flash(f"Connection {prefix}{next_no} created with meter MTR-{prefix[0]}-{next_no}.", "success")
        return redirect(url_for("staff.connections"))
    return render_template("staff/connection_form.html", customers=customers, utilities=utilities)


# ------------------------------------------------------------------ meter readings
@bp.route("/readings")
@login_required(*STAFF)
def readings():
    rows = query("""SELECT mr.*, m.meter_no, cu.full_name, u.name AS utility, u.unit, us.full_name AS recorded_by_name
                      FROM meter_readings mr
                      JOIN meters m ON m.meter_id = mr.meter_id
                      JOIN connections c ON c.connection_id = m.connection_id
                      JOIN customers cu ON cu.customer_id = c.customer_id
                      JOIN utilities u ON u.utility_id = c.utility_id
                      LEFT JOIN users us ON us.user_id = mr.recorded_by
                     ORDER BY mr.reading_id DESC LIMIT 100""")
    return render_template("staff/readings.html", readings=rows)


@bp.route("/readings/new", methods=["GET", "POST"])
@login_required(*STAFF)
def reading_new():
    meters = query("""SELECT m.meter_id, m.meter_no, cu.full_name, u.name AS utility FROM meters m
                        JOIN connections c ON c.connection_id = m.connection_id
                        JOIN customers cu ON cu.customer_id = c.customer_id
                        JOIN utilities u ON u.utility_id = c.utility_id
                       WHERE m.status = 'active' AND c.status = 'active' ORDER BY m.meter_no""")
    if request.method == "POST":
        f = request.form
        meter_id = int(f["meter_id"])
        previous = last_reading(meter_id)
        try:
            value = float(f["reading_value"])
        except ValueError:
            flash("Current reading must be a number.", "error")
            return render_template("staff/reading_form.html", meters=meters, form=f)

        db = get_db()
        try:
            cur = db.execute("""INSERT INTO meter_readings (meter_id, reading_date, previous_value, reading_value,
                                                            consumption, recorded_by, remarks)
                                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                             (meter_id, f["reading_date"], previous["value"], value,
                              round(value - previous["value"], 2), session["user_id"], f.get("remarks") or None))
            bill_id = generate_bill(db, cur.lastrowid, bill_date=date.today())
            meter_no = query("SELECT meter_no FROM meters WHERE meter_id = ?", (meter_id,), one=True)[0]
            log("Meter reading updated", f"Meter {meter_no}")
            db.commit()
        except sqlite3.IntegrityError as e:          # raised by our triggers / UNIQUE constraint
            db.rollback()
            msg = str(e)
            if "UNIQUE" in msg:
                msg = "A reading for this meter on this date already exists."
            flash(msg, "error")
            return render_template("staff/reading_form.html", meters=meters, form=f)
        flash("Reading saved and bill generated.", "success")
        return redirect(url_for("staff.bill_detail", bill_id=bill_id))
    return render_template("staff/reading_form.html", meters=meters,
                           form={"reading_date": date.today().isoformat()})


def last_reading(meter_id):
    row = query("""SELECT reading_value AS value, reading_date AS date FROM meter_readings
                    WHERE meter_id = ? ORDER BY reading_date DESC LIMIT 1""", (meter_id,), one=True)
    if row:
        return dict(row)
    meter = query("SELECT initial_reading, installed_on FROM meters WHERE meter_id = ?", (meter_id,), one=True) or abort(404)
    return {"value": meter["initial_reading"], "date": meter["installed_on"]}


@bp.route("/api/meters/<int:meter_id>")
@login_required(*STAFF)
def meter_info(meter_id):
    """Used by the reading form to show the previous reading as soon as a meter is picked."""
    info = query("""SELECT m.meter_no, cu.full_name, u.name AS utility, u.unit FROM meters m
                      JOIN connections c ON c.connection_id = m.connection_id
                      JOIN customers cu ON cu.customer_id = c.customer_id
                      JOIN utilities u ON u.utility_id = c.utility_id
                     WHERE m.meter_id = ?""", (meter_id,), one=True) or abort(404)
    prev = last_reading(meter_id)
    return jsonify(dict(info) | {"previous_value": prev["value"], "previous_date": prev["date"]})


# ------------------------------------------------------------------ billing and payments
@bp.route("/bills")
@login_required(*STAFF)
def bills():
    status = request.args.get("status", "")
    q = request.args.get("q", "").strip()
    like = f"%{q}%"
    rows = query("""SELECT * FROM v_bill_summary
                     WHERE (? = '' OR status = ?) AND (bill_no LIKE ? OR customer_name LIKE ? OR connection_no LIKE ?)
                     ORDER BY bill_id DESC LIMIT 200""", (status, status, like, like, like))
    return render_template("staff/bills.html", bills=rows, status=status, q=q)


@bp.route("/bills/<int:bill_id>")
@login_required(*STAFF)
def bill_detail(bill_id):
    return render_template("bill_detail.html", **load_bill(bill_id), back=url_for("staff.bills"))


def load_bill(bill_id):
    bill = query("""SELECT s.*, b.energy_charge, b.fixed_charge, b.tax_amount, cu.address, cu.phone,
                           mr.previous_value, mr.reading_value, mr.reading_date, m.meter_no
                      FROM v_bill_summary s
                      JOIN bills b ON b.bill_id = s.bill_id
                      JOIN customers cu ON cu.customer_id = s.customer_id
                      JOIN meter_readings mr ON mr.reading_id = b.reading_id
                      JOIN meters m ON m.meter_id = mr.meter_id
                     WHERE s.bill_id = ?""", (bill_id,), one=True) or abort(404)
    items = query("SELECT * FROM bill_items WHERE bill_id = ? ORDER BY item_id", (bill_id,))
    payments = query("SELECT * FROM payments WHERE bill_id = ? ORDER BY paid_at", (bill_id,))
    return {"bill": bill, "items": items, "payments": payments}


def record_payment(bill_id, amount, method, user_id):
    """Insert a payment. Returns (receipt_no, None) on success or (None, error message)."""
    db = get_db()
    today = datetime.now().strftime("%Y%m%d")
    count = query("SELECT COUNT(*) FROM payments WHERE receipt_no LIKE ?", (f"RCP{today}-%",), one=True)[0]
    receipt = f"RCP{today}-{count + 1:04d}"
    try:
        db.execute("INSERT INTO payments (receipt_no, bill_id, amount, method, recorded_by) VALUES (?, ?, ?, ?, ?)",
                   (receipt, bill_id, round(amount, 2), method, user_id))
        db.commit()
    except sqlite3.IntegrityError as e:              # trg_no_overpay or CHECK (amount > 0)
        db.rollback()
        return None, "Amount must be greater than zero." if "CHECK" in str(e) else str(e)
    return receipt, None


@bp.route("/bills/<int:bill_id>/pay", methods=["POST"])
@login_required(*STAFF)
def bill_pay(bill_id):
    try:
        amount = float(request.form["amount"])
    except ValueError:
        amount = 0
    receipt, error = record_payment(bill_id, amount, "cash", session["user_id"])
    flash(error or f"Counter payment recorded. Receipt {receipt}.", "error" if error else "success")
    return redirect(url_for("staff.bill_detail", bill_id=bill_id))


@bp.route("/payments")
@login_required(*STAFF)
def payments():
    rows = query("""SELECT p.*, s.bill_no, s.customer_name, s.utility FROM payments p
                      JOIN v_bill_summary s ON s.bill_id = p.bill_id
                     ORDER BY p.payment_id DESC LIMIT 200""")
    totals = query("SELECT method, COUNT(*) AS n, SUM(amount) AS total FROM payments GROUP BY method ORDER BY total DESC")
    return render_template("staff/payments.html", payments=rows, totals=totals)


# ------------------------------------------------------------------ complaints
@bp.route("/complaints")
@login_required(*STAFF)
def complaints():
    status = request.args.get("status", "")
    rows = query("""SELECT cp.*, cu.full_name, u.name AS utility, us.full_name AS assignee
                      FROM complaints cp
                      JOIN customers cu ON cu.customer_id = cp.customer_id
                      LEFT JOIN connections c ON c.connection_id = cp.connection_id
                      LEFT JOIN utilities u ON u.utility_id = c.utility_id
                      LEFT JOIN employees e ON e.employee_id = cp.assigned_to
                      LEFT JOIN users us ON us.user_id = e.user_id
                     WHERE (? = '' OR cp.status = ?)
                     ORDER BY cp.complaint_id DESC""", (status, status))
    counts = {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) AS n FROM complaints GROUP BY status")}
    counts[""] = sum(counts.values())
    return render_template("staff/complaints.html", complaints=rows, status=status, counts=counts)


@bp.route("/complaints/<int:complaint_id>", methods=["GET", "POST"])
@login_required(*STAFF)
def complaint_detail(complaint_id):
    complaint = query("""SELECT cp.*, cu.full_name, cu.phone, cu.address, u.name AS utility, c.connection_no
                           FROM complaints cp
                           JOIN customers cu ON cu.customer_id = cp.customer_id
                           LEFT JOIN connections c ON c.connection_id = cp.connection_id
                           LEFT JOIN utilities u ON u.utility_id = c.utility_id
                          WHERE cp.complaint_id = ?""", (complaint_id,), one=True) or abort(404)
    if request.method == "POST":
        f = request.form
        resolved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if f["status"] == "resolved" else None
        db = get_db()
        db.execute("""UPDATE complaints SET status = ?, priority = ?, assigned_to = ?, resolution = ?, resolved_at = ?
                       WHERE complaint_id = ?""",
                   (f["status"], f["priority"], f.get("assigned_to") or None, f.get("resolution") or None,
                    resolved_at, complaint_id))
        log("Complaint updated", f"{complaint['complaint_no']} - {f['status'].replace('_', ' ')}")
        db.commit()
        flash("Complaint updated.", "success")
        return redirect(url_for("staff.complaints"))
    employees = query("""SELECT e.employee_id, u.full_name, e.designation FROM employees e
                           JOIN users u ON u.user_id = e.user_id ORDER BY u.full_name""")
    return render_template("staff/complaint_detail.html", c=complaint, employees=employees)


# ------------------------------------------------------------------ outages
@bp.route("/outages")
@login_required(*STAFF)
def outages():
    status = request.args.get("status", "active")
    rows = query("""SELECT o.*, u.name AS utility,
                           (SELECT COUNT(*) FROM customers cu
                              JOIN connections c ON c.customer_id = cu.customer_id AND c.utility_id = o.utility_id
                             WHERE cu.area = o.area) AS affected
                      FROM outages o JOIN utilities u ON u.utility_id = o.utility_id
                     WHERE o.status = ? ORDER BY o.start_time DESC""", (status,))
    counts = {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) AS n FROM outages GROUP BY status")}
    return render_template("staff/outages.html", outages=rows, status=status, counts=counts)


@bp.route("/outages/new", methods=["GET", "POST"])
@login_required(*STAFF)
def outage_new():
    areas = [r[0] for r in query("SELECT DISTINCT area FROM customers ORDER BY area")]
    utilities = query("SELECT * FROM utilities ORDER BY utility_id")
    if request.method == "POST":
        f = request.form
        start, end = f["start_time"].replace("T", " "), f["estimated_end"].replace("T", " ")
        if end <= start:
            flash("Estimated end must be after the start time.", "error")
            return render_template("staff/outage_form.html", areas=areas, utilities=utilities, form=f)
        status = "scheduled" if start > datetime.now().strftime("%Y-%m-%d %H:%M") else "active"
        db = get_db()
        next_no = query("SELECT COALESCE(MAX(outage_id), 0) + 101 FROM outages", one=True)[0]
        db.execute("""INSERT INTO outages (outage_no, utility_id, area, reason, start_time, estimated_end, status, reported_by)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                   (f"OUT{next_no}", f["utility_id"], f["area"], f["reason"].strip(), start, end, status, session["user_id"]))
        db.commit()                                  # trg_outage_notify alerts customers in the area
        flash(f"Outage OUT{next_no} reported. Customers in {f['area']} have been notified.", "success")
        return redirect(url_for("staff.outages", status=status))
    return render_template("staff/outage_form.html", areas=areas, utilities=utilities, form={})


@bp.route("/outages/<int:outage_id>/resolve", methods=["POST"])
@login_required(*STAFF)
def outage_resolve(outage_id):
    db = get_db()
    db.execute("UPDATE outages SET status = 'resolved', resolved_at = datetime('now', 'localtime') WHERE outage_id = ?",
               (outage_id,))
    log("Outage resolved", query("SELECT outage_no FROM outages WHERE outage_id = ?", (outage_id,), one=True)[0])
    db.commit()
    flash("Outage marked as resolved.", "success")
    return redirect(url_for("staff.outages", status="resolved"))


# ------------------------------------------------------------------ admin only
@bp.route("/tariffs", methods=["GET", "POST"])
@login_required("admin")
def tariffs():
    db = get_db()
    if request.method == "POST":
        f = request.form
        try:
            for key, value in f.items():
                if key.startswith("rate_"):
                    db.execute("UPDATE tariff_slabs SET rate = ? WHERE slab_id = ?", (float(value), int(key[5:])))
            db.execute("UPDATE tariff_plans SET fixed_charge = ?, tax_percent = ? WHERE tariff_id = ?",
                       (float(f["fixed_charge"]), float(f["tax_percent"]), int(f["tariff_id"])))
            log("Tariff updated", f"Plan #{f['tariff_id']}")
            db.commit()
            flash("Tariff saved. New rates apply to bills generated from now on.", "success")
        except (ValueError, sqlite3.IntegrityError):
            db.rollback()
            flash("Rates must be non-negative numbers.", "error")
        return redirect(url_for("staff.tariffs"))
    plans = query("""SELECT t.*, u.name AS utility, u.unit FROM tariff_plans t
                       JOIN utilities u ON u.utility_id = t.utility_id ORDER BY t.utility_id, t.category""")
    slabs = {}
    for s in query("SELECT * FROM tariff_slabs ORDER BY tariff_id, from_unit"):
        slabs.setdefault(s["tariff_id"], []).append(s)
    return render_template("staff/tariffs.html", plans=plans, slabs=slabs)


@bp.route("/employees", methods=["GET", "POST"])
@login_required("admin")
def employees():
    db = get_db()
    if request.method == "POST":
        f = request.form
        try:
            cur = db.execute("INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, 'employee', ?)",
                             (f["username"].strip().lower(), generate_password_hash(f["password"]), f["full_name"].strip()))
            next_no = query("SELECT COALESCE(MAX(employee_id), 0) + 101 FROM employees", one=True)[0]
            db.execute("INSERT INTO employees (user_id, emp_code, designation, phone, area) VALUES (?, ?, ?, ?, ?)",
                       (cur.lastrowid, f"E{next_no}", f["designation"], f["phone"], f.get("area") or None))
            db.commit()
            flash(f"Employee E{next_no} added.", "success")
        except sqlite3.IntegrityError:
            db.rollback()
            flash("That username is already taken.", "error")
        return redirect(url_for("staff.employees"))
    rows = query("""SELECT e.*, u.full_name, u.username,
                           (SELECT COUNT(*) FROM meter_readings mr WHERE mr.recorded_by = u.user_id) AS n_readings,
                           (SELECT COUNT(*) FROM complaints cp WHERE cp.assigned_to = e.employee_id
                                                                AND cp.status <> 'resolved') AS n_open
                      FROM employees e JOIN users u ON u.user_id = e.user_id ORDER BY e.emp_code""")
    return render_template("staff/employees.html", employees=rows)


@bp.route("/reports")
@login_required("admin")
def reports():
    months = last_months(6)
    start = months[0] if months else "0000-00"
    totals = query("""SELECT utility, unit, SUM(total_units) AS units, SUM(total_billed) AS billed
                        FROM v_monthly_consumption WHERE billing_month >= ? GROUP BY utility, unit
                       ORDER BY CASE utility WHEN 'Electricity' THEN 1 WHEN 'Water' THEN 2 ELSE 3 END""", (start,))
    by_area = query("""SELECT area, ROUND(SUM(units), 1) AS units FROM v_bill_summary
                        WHERE utility = 'Electricity' AND billing_month >= ? GROUP BY area ORDER BY units DESC""", (start,))
    by_category = query("""SELECT category, ROUND(SUM(total_amount), 2) AS billed FROM v_bill_summary
                            WHERE billing_month >= ? GROUP BY category""", (start,))
    collection = query("""SELECT ROUND(SUM(total_amount), 2) AS billed, ROUND(SUM(amount_paid), 2) AS paid
                            FROM bills WHERE billing_month >= ?""", (start,), one=True)
    overdue = query("SELECT * FROM v_overdue_bills ORDER BY days_overdue DESC LIMIT 15")
    return render_template("staff/reports.html", months=months, totals=totals, collection=collection, overdue=overdue,
                           by_area=[dict(r) for r in by_area], by_category=[dict(r) for r in by_category])
