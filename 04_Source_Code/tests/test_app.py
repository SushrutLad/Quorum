"""Functional tests that drive the real Flask app and SQLite database."""
from datetime import date, timedelta

from conftest import login

TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def sushrut_meter(db, utility_id=1):
    """Sushrut Lad (customer C1001): the meter and its last reading for one utility."""
    return db.execute("""SELECT m.meter_id, MAX(mr.reading_value) AS last FROM meters m
                           JOIN connections c ON c.connection_id = m.connection_id
                           JOIN meter_readings mr ON mr.meter_id = m.meter_id
                          WHERE c.customer_id = 1 AND c.utility_id = ?""", (utility_id,)).fetchone()


# ---------------------------------------------------------------- login and access control
def test_it01_valid_login_goes_to_dashboard(client):
    r = login(client, "admin", "admin123")
    assert r.status_code == 302 and r.headers["Location"].endswith("/staff/dashboard")
    assert b"Dashboard" in client.get("/staff/dashboard").data


def test_it02_wrong_password_rejected(client):
    r = login(client, "admin", "wrong")
    assert r.status_code == 200 and b"Invalid username or password" in r.data


def test_it03_not_logged_in_redirects_to_login(client):
    r = client.get("/staff/bills")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_it04_role_checks(client):
    login(client, "sushrut@example.com", "pass123")
    assert client.get("/staff/dashboard").status_code == 403
    login(client, "reader", "reader123")
    assert client.get("/staff/tariffs").status_code == 403       # admin only
    assert client.get("/staff/readings/new").status_code == 200


def test_it05_customer_cannot_see_other_customers_bill(client, db):
    # a bill that belongs to Sumit P Surendran (customer C1002)
    other = db.execute("""SELECT b.bill_id FROM bills b JOIN connections c ON c.connection_id = b.connection_id
                           WHERE c.customer_id = 2 LIMIT 1""").fetchone()[0]
    login(client, "sushrut@example.com", "pass123")
    assert client.get(f"/my/bills/{other}").status_code == 403
    assert client.get(f"/my/bills/{other}/pay").status_code == 403


# ---------------------------------------------------------------- end-to-end: reading -> bill -> payment
def test_it06_reading_to_bill_to_payment(client, db):
    meter = sushrut_meter(db)
    login(client, "reader", "reader123")
    r = client.post("/staff/readings/new", data={"meter_id": meter["meter_id"], "reading_value": meter["last"] + 250,
                                                 "reading_date": TOMORROW})
    assert r.status_code == 302 and "/staff/bills/" in r.headers["Location"]

    bill = db.execute("SELECT * FROM bills ORDER BY bill_id DESC LIMIT 1").fetchone()
    assert bill["units"] == 250 and bill["total_amount"] == 1207.50 and bill["status"] == "unpaid"

    login(client, "sushrut@example.com", "pass123")
    assert bill["bill_no"].encode() in client.get("/my/bills").data
    r = client.post(f"/my/bills/{bill['bill_id']}/pay", data={"method": "upi", "amount": "1207.50"})
    assert r.status_code == 302

    bill = db.execute("SELECT status, amount_paid FROM bills WHERE bill_id = ?", (bill["bill_id"],)).fetchone()
    assert bill["status"] == "paid" and bill["amount_paid"] == 1207.50
    note = db.execute("SELECT title FROM notifications WHERE user_id = (SELECT user_id FROM customers WHERE customer_id = 1) "
                      "ORDER BY notification_id DESC LIMIT 1").fetchone()
    assert note["title"] == "Payment received"


def test_it07_lower_reading_rejected(client, db):
    meter = sushrut_meter(db)
    before = db.execute("SELECT COUNT(*) FROM bills").fetchone()[0]
    login(client, "reader", "reader123")
    r = client.post("/staff/readings/new", data={"meter_id": meter["meter_id"], "reading_value": meter["last"] - 10,
                                                 "reading_date": TOMORROW})
    assert b"Reading cannot be lower than the previous reading" in r.data
    assert db.execute("SELECT COUNT(*) FROM bills").fetchone()[0] == before


def test_it08_reading_date_must_move_forward(client, db):
    meter = sushrut_meter(db)
    login(client, "reader", "reader123")
    r = client.post("/staff/readings/new", data={"meter_id": meter["meter_id"], "reading_value": meter["last"] + 10,
                                                 "reading_date": "2020-01-01"})
    assert b"Reading date must be after the last reading date" in r.data


def test_it09_overpayment_rejected(client, db):
    bill = db.execute("""SELECT b.bill_id, b.total_amount - b.amount_paid AS due FROM bills b
                           JOIN connections c ON c.connection_id = b.connection_id
                          WHERE c.customer_id = 1 AND b.status <> 'paid' LIMIT 1""").fetchone()
    login(client, "sushrut@example.com", "pass123")
    r = client.post(f"/my/bills/{bill['bill_id']}/pay", data={"method": "card", "amount": bill["due"] + 100})
    assert b"Payment exceeds outstanding balance" in r.data
    assert db.execute("SELECT status FROM bills WHERE bill_id = ?", (bill["bill_id"],)).fetchone()[0] != "paid"


def test_it10_partial_payment(client, db):
    bill = db.execute("SELECT bill_id, total_amount FROM bills WHERE status = 'unpaid' LIMIT 1").fetchone()
    login(client, "billing", "billing123")
    client.post(f"/staff/bills/{bill['bill_id']}/pay", data={"amount": round(bill["total_amount"] / 2, 2)})
    assert db.execute("SELECT status FROM bills WHERE bill_id = ?", (bill["bill_id"],)).fetchone()[0] == "partial"


# ---------------------------------------------------------------- other features
def test_it11_outage_notifies_only_that_area(client, db):
    def count(area):
        return db.execute("""SELECT COUNT(*) FROM notifications n JOIN customers c ON c.user_id = n.user_id
                              WHERE c.area = ? AND n.title = 'Outage in your area'""", (area,)).fetchone()[0]
    before_alambagh, before_hazratganj = count("Alambagh"), count("Hazratganj")
    login(client, "admin", "admin123")
    client.post("/staff/outages/new", data={"utility_id": 1, "area": "Alambagh", "reason": "Test fault",
                                            "start_time": "2026-01-01T10:00", "estimated_end": "2026-01-01T12:00"})
    expected = db.execute("""SELECT COUNT(*) FROM customers cu JOIN connections c ON c.customer_id = cu.customer_id
                              WHERE cu.area = 'Alambagh' AND c.utility_id = 1""").fetchone()[0]
    assert count("Alambagh") - before_alambagh == expected > 0
    assert count("Hazratganj") == before_hazratganj


def test_it12_complaint_lifecycle(client, db):
    login(client, "sushrut@example.com", "pass123")
    client.post("/my/complaints", data={"connection_id": 1, "issue": "Meter sparking", "priority": "high"})
    complaint = db.execute("SELECT * FROM complaints ORDER BY complaint_id DESC LIMIT 1").fetchone()
    assert complaint["issue"] == "Meter sparking" and complaint["status"] == "open"

    login(client, "tech", "tech123")
    assert b"Meter sparking" in client.get("/staff/complaints").data
    client.post(f"/staff/complaints/{complaint['complaint_id']}",
                data={"status": "resolved", "priority": "high", "assigned_to": 3, "resolution": "Replaced wiring"})
    row = db.execute("SELECT status, resolved_at FROM complaints WHERE complaint_id = ?",
                     (complaint["complaint_id"],)).fetchone()
    assert row["status"] == "resolved" and row["resolved_at"]


def test_it13_duplicate_customer_email_rejected(client, db):
    login(client, "admin", "admin123")
    before = db.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    r = client.post("/staff/customers/new", data={"full_name": "Sushrut Lad", "email": "sushrut@example.com", "phone": "9999999999",
                                                  "address": "x", "area": "Aliganj", "category": "residential",
                                                  "password": "secret1"})
    assert b"already exists" in r.data
    assert db.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == before


def test_it14_tariff_change_does_not_alter_old_bills(client, db):
    old = db.execute("SELECT bill_id, total_amount FROM bills WHERE bill_id = 1").fetchone()
    slab = db.execute("SELECT slab_id FROM tariff_slabs WHERE tariff_id = 1 ORDER BY from_unit LIMIT 1").fetchone()[0]
    login(client, "admin", "admin123")
    client.post("/staff/tariffs", data={"tariff_id": 1, f"rate_{slab}": "9.99", "fixed_charge": "50", "tax_percent": "5"})
    assert db.execute("SELECT rate FROM tariff_slabs WHERE slab_id = ?", (slab,)).fetchone()[0] == 9.99
    assert db.execute("SELECT total_amount FROM bills WHERE bill_id = 1").fetchone()[0] == old["total_amount"]
