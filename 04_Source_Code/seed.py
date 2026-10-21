"""Create the database and fill it with demo data.

    python seed.py            -> creates eums.db next to this file
    python seed.py other.db   -> creates the given file instead

WARNING: this deletes all existing data in that database.
"""
import csv
import os
import random
import sys
from datetime import date, datetime, timedelta

from werkzeug.security import generate_password_hash

from billing import generate_bill
from db import connect

HERE = os.path.dirname(os.path.abspath(__file__))

UTILITIES = [(1, "Electricity", "kWh"), (2, "Water", "kL"), (3, "Gas", "SCM")]

# (utility_id, category, name, fixed charge, tax %, [(from, to, rate), ...])
TARIFFS = [
    (1, "residential", "Domestic Electricity (LMV-1)", 50, 5, [(0, 100, 3.50), (100, 300, 5.00), (300, None, 7.00)]),
    (1, "commercial", "Commercial Electricity (LMV-2)", 150, 5, [(0, 200, 6.50), (200, None, 8.00)]),
    (2, "residential", "Domestic Water", 40, 0, [(0, 10, 8.00), (10, 20, 12.00), (20, None, 18.00)]),
    (2, "commercial", "Commercial Water", 100, 0, [(0, None, 20.00)]),
    (3, "residential", "Domestic PNG", 30, 5, [(0, 25, 45.00), (25, None, 52.00)]),
    (3, "commercial", "Commercial PNG", 100, 5, [(0, None, 60.00)]),
]

# Typical monthly use (low, high) by utility and category
USAGE = {(1, "residential"): (110, 340), (1, "commercial"): (450, 900),
         (2, "residential"): (8, 24), (2, "commercial"): (30, 60),
         (3, "residential"): (14, 38), (3, "commercial"): (60, 120)}

STAFF = [  # username, password, full name, designation, area
    ("reader", "reader123", "Suresh Yadav", "Meter Reader", "Gomti Nagar"),
    ("billing", "billing123", "Anjali Mehta", "Billing Officer", None),
    ("tech", "tech123", "Ramesh Patel", "Technician", "Aliganj"),
    ("tech2", "tech123", "Deepak Rawat", "Technician", "Hazratganj"),
]

MONTHS_OF_HISTORY = 6


def month_start(d, back):
    """First day of the month `back` months before d."""
    y, m = d.year, d.month - back
    while m < 1:
        y, m = y - 1, m + 12
    return date(y, m, 1)


def seed(path):
    random.seed(42)
    today = date.today()
    if os.path.exists(path):
        os.remove(path)
    db = connect(path)
    with open(os.path.join(HERE, "schema.sql")) as f:
        db.executescript(f.read())

    db.executemany("INSERT INTO utilities VALUES (?, ?, ?)", UTILITIES)
    tariff_ids = {}
    for utility_id, category, name, fixed, tax, slabs in TARIFFS:
        cur = db.execute("INSERT INTO tariff_plans (utility_id, category, name, fixed_charge, tax_percent) "
                         "VALUES (?, ?, ?, ?, ?)", (utility_id, category, name, fixed, tax))
        tariff_ids[(utility_id, category)] = cur.lastrowid
        db.executemany("INSERT INTO tariff_slabs (tariff_id, from_unit, to_unit, rate) VALUES (?, ?, ?, ?)",
                       [(cur.lastrowid, *s) for s in slabs])

    # ---- staff
    db.execute("INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, 'admin', ?)",
               ("admin", generate_password_hash("admin123"), "System Administrator"))
    employee_ids, staff_user_ids = [], []
    for i, (username, pw, name, designation, area) in enumerate(STAFF):
        cur = db.execute("INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, 'employee', ?)",
                         (username, generate_password_hash(pw), name))
        staff_user_ids.append(cur.lastrowid)
        cur = db.execute("INSERT INTO employees (user_id, emp_code, designation, phone, area) VALUES (?, ?, ?, ?, ?)",
                         (staff_user_ids[-1], f"E{101 + i}", designation, f"98390{10001 + i}", area))
        employee_ids.append(cur.lastrowid)
    reader_user = staff_user_ids[0]

    # ---- customers, connections, meters
    first_month = month_start(today, MONTHS_OF_HISTORY)
    install_date = first_month - timedelta(days=20)
    meters = []          # (meter_id, connection_id, utility_id, category, customer_id)
    customer_pw = generate_password_hash("pass123")
    with open(os.path.join(HERE, "sample_data", "customers.csv"), newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            cur = db.execute("INSERT INTO users (username, password_hash, role, full_name, created_at) "
                             "VALUES (?, ?, 'customer', ?, ?)",
                             (row["email"], customer_pw, row["full_name"], f"{install_date} 10:00:00"))
            cur = db.execute("""INSERT INTO customers (user_id, customer_code, full_name, phone, email, address, area,
                                                       category, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                             (cur.lastrowid, f"C{1001 + i}", row["full_name"], row["phone"], row["email"],
                              row["address"], row["area"], row["category"], f"{install_date} 10:00:00"))
            customer_id = cur.lastrowid
            for code in row["utilities"].split(";"):
                utility_id = {"E": 1, "W": 2, "G": 3}[code]
                prefix = {"E": "ELEC", "W": "WATE", "G": "GAS"}[code]
                n = db.execute("SELECT COALESCE(MAX(connection_id), 0) + 1001 FROM connections").fetchone()[0]
                cur = db.execute("""INSERT INTO connections (connection_no, customer_id, utility_id, tariff_id, installed_on)
                                    VALUES (?, ?, ?, ?, ?)""",
                                 (f"{prefix}{n}", customer_id, utility_id,
                                  tariff_ids[(utility_id, row["category"])], install_date.isoformat()))
                connection_id = cur.lastrowid
                start = round(random.uniform(1000, 15000) if utility_id == 1 else random.uniform(50, 900), 1)
                cur = db.execute("INSERT INTO meters (meter_no, connection_id, initial_reading, installed_on) "
                                 "VALUES (?, ?, ?, ?)", (f"MTR-{code}-{n}", connection_id, start, install_date.isoformat()))
                meters.append((cur.lastrowid, connection_id, utility_id, row["category"], customer_id))

    # ---- monthly readings -> bills -> payments
    for back in range(MONTHS_OF_HISTORY - 1, -1, -1):
        read_on = month_start(today, back) + timedelta(days=1)   # readings taken on the 2nd
        if read_on > today:
            continue
        season = 1.25 if read_on.month in (5, 6, 7, 8) else 0.9 if read_on.month in (12, 1, 2) else 1.0
        for meter_id, connection_id, utility_id, category, customer_id in meters:
            low, high = USAGE[(utility_id, category)]
            factor = season if utility_id == 1 else (2 - season) if utility_id == 3 else 1
            use = round(random.uniform(low, high) * factor, 1)
            prev = db.execute("SELECT COALESCE(MAX(reading_value), (SELECT initial_reading FROM meters WHERE meter_id = ?)) "
                              "FROM meter_readings WHERE meter_id = ?", (meter_id, meter_id)).fetchone()[0]
            cur = db.execute("""INSERT INTO meter_readings (meter_id, reading_date, previous_value, reading_value,
                                                            consumption, recorded_by)
                                VALUES (?, ?, ?, ?, ?, ?)""",
                             (meter_id, read_on.isoformat(), prev, round(prev + use, 1), use, reader_user))
            bill_id = generate_bill(db, cur.lastrowid, bill_date=read_on)
            total = db.execute("SELECT total_amount FROM bills WHERE bill_id = ?", (bill_id,)).fetchone()[0]

            # Older bills are mostly paid; the latest month is mostly still open.
            chance = 0.45 if back == 0 else 0.93
            if random.random() < chance:
                paid_on = read_on + timedelta(days=random.randint(1, 14))
                if paid_on > today:
                    continue
                method = random.choice(["upi", "upi", "upi", "card", "netbanking", "wallet", "cash"])
                amount = total if random.random() > 0.05 else round(total / 2, 2)
                n = db.execute("SELECT COUNT(*) FROM payments").fetchone()[0] + 1
                db.execute("INSERT INTO payments (receipt_no, bill_id, amount, method, paid_at, recorded_by) "
                           "VALUES (?, ?, ?, ?, ?, ?)",
                           (f"RCP{paid_on:%Y%m%d}-{n:04d}", bill_id, amount, method,
                            f"{paid_on} {random.randint(9, 20):02d}:{random.randint(0, 59):02d}:00",
                            reader_user if method == "cash" else None))

    # ---- complaints
    complaint_rows = [
        (2, 2, "Low water pressure", "Pressure very low in the mornings.", "high", "open", None),
        (2, 1, "Power fluctuation", "Voltage keeps dropping in the evening.", "medium", "in_progress", 0),
        (3, 2, "Gas leakage smell near meter", "Smell near the meter box.", "high", "open", None),
        (4, 1, "No water supply", "No supply since yesterday.", "low", "resolved", 3),
        (1, 1, "Wrong bill amount", "Bill seems higher than usual.", "medium", "in_progress", 1),
        (6, 1, "Meter not working", "Meter display is blank.", "high", "open", None),
        (7, 3, "Gas pressure low", "Flame is weak.", "medium", "resolved", 2),
        (9, 2, "Dirty water", "Water is muddy.", "high", "in_progress", 3),
        (12, 1, "Frequent power cuts", "3-4 cuts every day.", "medium", "open", None),
        (13, 2, "Pipeline leakage", "Leak outside the house.", "high", "resolved", 2),
        (16, 3, "Bill not received", "Did not get last month bill.", "low", "resolved", 1),
        (18, 1, "Streetlight connection issue", "Pole wire loose.", "low", "open", None),
    ]
    for i, (cust, util, issue, desc, prio, status, emp) in enumerate(complaint_rows):
        conn = db.execute("SELECT connection_id FROM connections WHERE customer_id = ? AND utility_id = ?",
                          (cust, util)).fetchone()
        created = datetime.now() - timedelta(days=len(complaint_rows) - i, hours=random.randint(0, 8))
        resolved = (created + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S") if status == "resolved" else None
        db.execute("""INSERT INTO complaints (complaint_no, customer_id, connection_id, issue, description, priority,
                                              status, assigned_to, resolution, created_at, resolved_at)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                   (f"CMP{4501 + i}", cust, conn[0] if conn else None, issue, desc, prio, status,
                    employee_ids[emp] if emp is not None else None,
                    "Fixed on site visit." if status == "resolved" else None,
                    created.strftime("%Y-%m-%d %H:%M:%S"), resolved))

    # ---- outages
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    fmt = "%Y-%m-%d %H:%M"
    outage_rows = [
        (1, "Gomti Nagar", "Transformer fault", now - timedelta(hours=3), now + timedelta(hours=2), "active", None),
        (2, "Aliganj", "Main pipeline repair", now - timedelta(hours=5), now + timedelta(hours=4), "active", None),
        (1, "Indira Nagar", "Scheduled line maintenance", now + timedelta(days=1), now + timedelta(days=1, hours=4),
         "scheduled", None),
        (3, "Hazratganj", "Pressure regulator replacement", now - timedelta(days=4), now - timedelta(days=4, hours=-3),
         "resolved", now - timedelta(days=4, hours=-2)),
        (1, "Alambagh", "Cable fault", now - timedelta(days=8), now - timedelta(days=8, hours=-4),
         "resolved", now - timedelta(days=8, hours=-5)),
    ]
    for i, (util, area, reason, start, end, status, resolved_at) in enumerate(outage_rows):
        db.execute("""INSERT INTO outages (outage_no, utility_id, area, reason, start_time, estimated_end, status,
                                           resolved_at, reported_by)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                   (f"OUT{101 + i}", util, area, reason, start.strftime(fmt), end.strftime(fmt), status,
                    resolved_at.strftime(fmt) if resolved_at else None))

    # Older notifications count as already read; keep the last few unread for the demo.
    db.execute("UPDATE notifications SET is_read = 1 WHERE notification_id NOT IN "
               "(SELECT MAX(notification_id) FROM notifications GROUP BY user_id)")
    db.execute("DELETE FROM audit_log")
    db.executemany("INSERT INTO audit_log (action, details, created_at) VALUES (?, ?, ?)", [
        ("New customer registered", "Green Leaf Cafe", (datetime.now() - timedelta(hours=6)).strftime(fmt)),
        ("Bill payment received", "Rs 1,240.00 - Sushrut Lad", (datetime.now() - timedelta(hours=4)).strftime(fmt)),
        ("New complaint submitted", "Low water pressure - #CMP4501", (datetime.now() - timedelta(hours=3)).strftime(fmt)),
        ("Meter reading updated", "Meter MTR-E-1001", (datetime.now() - timedelta(hours=2)).strftime(fmt)),
        ("Outage reported", "Area: Gomti Nagar", (datetime.now() - timedelta(hours=1)).strftime(fmt)),
    ])
    db.commit()
    db.close()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "eums.db")
    seed(target)
    print(f"Database created at {target}")
    print("Logins: admin/admin123, reader/reader123, sushrut@example.com/pass123")
