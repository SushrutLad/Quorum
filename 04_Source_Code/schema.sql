-- Energy & Utility Management System (EUMS) - database schema (SQLite)
-- Run automatically by seed.py. Tables are in 3NF except `bills`, which keeps a
-- snapshot of the charges so old bills do not change when tariffs change.

PRAGMA foreign_keys = ON;

DROP VIEW IF EXISTS v_bill_summary;
DROP VIEW IF EXISTS v_overdue_bills;
DROP VIEW IF EXISTS v_monthly_consumption;
DROP TABLE IF EXISTS audit_log;
DROP TABLE IF EXISTS notifications;
DROP TABLE IF EXISTS outages;
DROP TABLE IF EXISTS complaints;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS bill_items;
DROP TABLE IF EXISTS bills;
DROP TABLE IF EXISTS meter_readings;
DROP TABLE IF EXISTS meters;
DROP TABLE IF EXISTS connections;
DROP TABLE IF EXISTS tariff_slabs;
DROP TABLE IF EXISTS tariff_plans;
DROP TABLE IF EXISTS utilities;
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS users;

-- ---------------------------------------------------------------- people
CREATE TABLE users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,          -- login id (email for customers)
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('admin', 'employee', 'customer')),
    full_name     TEXT    NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL UNIQUE REFERENCES users(user_id),
    customer_code TEXT    NOT NULL UNIQUE,          -- e.g. C1001
    full_name     TEXT    NOT NULL,
    phone         TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    address       TEXT    NOT NULL,
    area          TEXT    NOT NULL,
    category      TEXT    NOT NULL CHECK (category IN ('residential', 'commercial')),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE employees (
    employee_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL UNIQUE REFERENCES users(user_id),
    emp_code      TEXT    NOT NULL UNIQUE,          -- e.g. E101
    designation   TEXT    NOT NULL,                 -- Meter Reader, Billing Officer, Technician
    phone         TEXT    NOT NULL,
    area          TEXT
);

-- ---------------------------------------------------------------- tariffs
CREATE TABLE utilities (
    utility_id    INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,             -- Electricity, Water, Gas
    unit          TEXT NOT NULL                     -- kWh, kL, SCM
);

CREATE TABLE tariff_plans (
    tariff_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    utility_id    INTEGER NOT NULL REFERENCES utilities(utility_id),
    category      TEXT    NOT NULL CHECK (category IN ('residential', 'commercial')),
    name          TEXT    NOT NULL,
    fixed_charge  REAL    NOT NULL CHECK (fixed_charge >= 0),
    tax_percent   REAL    NOT NULL CHECK (tax_percent >= 0),
    UNIQUE (utility_id, category)
);

CREATE TABLE tariff_slabs (
    slab_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    tariff_id     INTEGER NOT NULL REFERENCES tariff_plans(tariff_id) ON DELETE CASCADE,
    from_unit     REAL    NOT NULL CHECK (from_unit >= 0),
    to_unit       REAL,                             -- NULL means "and above"
    rate          REAL    NOT NULL CHECK (rate >= 0),
    CHECK (to_unit IS NULL OR to_unit > from_unit)
);

-- ---------------------------------------------------------------- connections and meters
CREATE TABLE connections (
    connection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_no TEXT    NOT NULL UNIQUE,          -- e.g. ELEC1001
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    utility_id    INTEGER NOT NULL REFERENCES utilities(utility_id),
    tariff_id     INTEGER NOT NULL REFERENCES tariff_plans(tariff_id),
    status        TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disconnected')),
    installed_on  TEXT    NOT NULL,
    UNIQUE (customer_id, utility_id)                -- one connection per utility per customer
);

CREATE TABLE meters (
    meter_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    meter_no        TEXT    NOT NULL UNIQUE,        -- e.g. MTR-E-1001
    connection_id   INTEGER NOT NULL REFERENCES connections(connection_id),
    initial_reading REAL    NOT NULL DEFAULT 0 CHECK (initial_reading >= 0),
    status          TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'faulty', 'replaced')),
    installed_on    TEXT    NOT NULL
);

CREATE TABLE meter_readings (
    reading_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    meter_id       INTEGER NOT NULL REFERENCES meters(meter_id),
    reading_date   TEXT    NOT NULL,
    previous_value REAL    NOT NULL,
    reading_value  REAL    NOT NULL,
    consumption    REAL    NOT NULL CHECK (consumption >= 0),
    recorded_by    INTEGER REFERENCES users(user_id),
    remarks        TEXT,
    UNIQUE (meter_id, reading_date)
);

-- ---------------------------------------------------------------- billing
CREATE TABLE bills (
    bill_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_no        TEXT    NOT NULL UNIQUE,         -- e.g. BILL202503-0001
    connection_id  INTEGER NOT NULL REFERENCES connections(connection_id),
    reading_id     INTEGER NOT NULL UNIQUE REFERENCES meter_readings(reading_id),
    billing_month  TEXT    NOT NULL,                -- YYYY-MM
    bill_date      TEXT    NOT NULL,
    due_date       TEXT    NOT NULL,
    units          REAL    NOT NULL,
    energy_charge  REAL    NOT NULL,                -- snapshot (deliberate denormalisation)
    fixed_charge   REAL    NOT NULL,
    tax_amount     REAL    NOT NULL,
    total_amount   REAL    NOT NULL CHECK (total_amount >= 0),
    amount_paid    REAL    NOT NULL DEFAULT 0,
    status         TEXT    NOT NULL DEFAULT 'unpaid' CHECK (status IN ('unpaid', 'partial', 'paid'))
);

CREATE TABLE bill_items (
    item_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id        INTEGER NOT NULL REFERENCES bills(bill_id) ON DELETE CASCADE,
    description    TEXT    NOT NULL,
    units          REAL,
    rate           REAL,
    amount         REAL    NOT NULL
);

CREATE TABLE payments (
    payment_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_no     TEXT    NOT NULL UNIQUE,         -- e.g. RCP20250314-0001
    bill_id        INTEGER NOT NULL REFERENCES bills(bill_id),
    amount         REAL    NOT NULL CHECK (amount > 0),
    method         TEXT    NOT NULL CHECK (method IN ('card', 'upi', 'netbanking', 'wallet', 'cash')),
    paid_at        TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    recorded_by    INTEGER REFERENCES users(user_id)
);

-- ---------------------------------------------------------------- service
CREATE TABLE complaints (
    complaint_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_no   TEXT    NOT NULL UNIQUE,         -- e.g. CMP4521
    customer_id    INTEGER NOT NULL REFERENCES customers(customer_id),
    connection_id  INTEGER REFERENCES connections(connection_id),
    issue          TEXT    NOT NULL,
    description    TEXT,
    priority       TEXT    NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high')),
    status         TEXT    NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved')),
    assigned_to    INTEGER REFERENCES employees(employee_id),
    resolution     TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    resolved_at    TEXT
);

CREATE TABLE outages (
    outage_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    outage_no      TEXT    NOT NULL UNIQUE,         -- e.g. OUT102
    utility_id     INTEGER NOT NULL REFERENCES utilities(utility_id),
    area           TEXT    NOT NULL,
    reason         TEXT    NOT NULL,
    start_time     TEXT    NOT NULL,
    estimated_end  TEXT    NOT NULL,
    status         TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('scheduled', 'active', 'resolved')),
    resolved_at    TEXT,
    reported_by    INTEGER REFERENCES users(user_id)
);

CREATE TABLE notifications (
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(user_id),
    title           TEXT    NOT NULL,
    message         TEXT    NOT NULL,
    is_read         INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE audit_log (
    log_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    action         TEXT    NOT NULL,                -- short title shown on the dashboard
    details        TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ---------------------------------------------------------------- indexes
CREATE INDEX idx_readings_meter_date ON meter_readings(meter_id, reading_date);
CREATE INDEX idx_bills_status_due    ON bills(status, due_date);
CREATE INDEX idx_bills_month         ON bills(billing_month);
CREATE INDEX idx_customers_area      ON customers(area);
CREATE INDEX idx_complaints_status   ON complaints(status);
CREATE INDEX idx_notifications_user  ON notifications(user_id, is_read);

-- ---------------------------------------------------------------- triggers
-- T1: a meter is cumulative, so a new reading can never be lower than the last one.
CREATE TRIGGER trg_reading_monotonic
BEFORE INSERT ON meter_readings
WHEN NEW.reading_value < COALESCE(
        (SELECT MAX(reading_value) FROM meter_readings WHERE meter_id = NEW.meter_id),
        (SELECT initial_reading FROM meters WHERE meter_id = NEW.meter_id))
BEGIN
    SELECT RAISE(ABORT, 'Reading cannot be lower than the previous reading');
END;

-- T2: readings must be entered in date order.
CREATE TRIGGER trg_reading_date_order
BEFORE INSERT ON meter_readings
WHEN NEW.reading_date <= (SELECT MAX(reading_date) FROM meter_readings WHERE meter_id = NEW.meter_id)
BEGIN
    SELECT RAISE(ABORT, 'Reading date must be after the last reading date');
END;

-- T3: a payment can never be larger than what is still owed on the bill.
CREATE TRIGGER trg_no_overpay
BEFORE INSERT ON payments
WHEN NEW.amount > (SELECT ROUND(total_amount - amount_paid, 2) FROM bills WHERE bill_id = NEW.bill_id) + 0.001
BEGIN
    SELECT RAISE(ABORT, 'Payment exceeds outstanding balance');
END;

-- T4: after a payment, update the bill and tell the customer.
CREATE TRIGGER trg_payment_status
AFTER INSERT ON payments
BEGIN
    UPDATE bills
       SET amount_paid = ROUND(amount_paid + NEW.amount, 2),
           status = CASE WHEN ROUND(amount_paid + NEW.amount, 2) >= total_amount THEN 'paid' ELSE 'partial' END
     WHERE bill_id = NEW.bill_id;

    INSERT INTO notifications (user_id, title, message)
    SELECT cu.user_id, 'Payment received',
           'Rs ' || printf('%.2f', NEW.amount) || ' received for bill ' || b.bill_no || ' (receipt ' || NEW.receipt_no || ').'
      FROM bills b
      JOIN connections c ON c.connection_id = b.connection_id
      JOIN customers cu  ON cu.customer_id  = c.customer_id
     WHERE b.bill_id = NEW.bill_id;

    INSERT INTO audit_log (action, details)
    SELECT 'Bill payment received', 'Rs ' || printf('%.2f', NEW.amount) || ' - ' || b.bill_no
      FROM bills b WHERE b.bill_id = NEW.bill_id;
END;

-- T5: tell the customer when a new bill is generated.
CREATE TRIGGER trg_bill_notify
AFTER INSERT ON bills
BEGIN
    INSERT INTO notifications (user_id, title, message)
    SELECT cu.user_id, 'New bill generated',
           'Bill ' || NEW.bill_no || ' for ' || NEW.billing_month || ' is Rs ' || printf('%.2f', NEW.total_amount) || ', due ' || NEW.due_date || '.'
      FROM connections c
      JOIN customers cu ON cu.customer_id = c.customer_id
     WHERE c.connection_id = NEW.connection_id;
END;

-- T6: when an outage is reported, alert every customer in that area who has that utility.
CREATE TRIGGER trg_outage_notify
AFTER INSERT ON outages
BEGIN
    INSERT INTO notifications (user_id, title, message)
    SELECT cu.user_id, 'Outage in your area',
           u.name || ' supply affected in ' || NEW.area || ': ' || NEW.reason || '. Expected restoration ' || NEW.estimated_end || '.'
      FROM customers cu
      JOIN connections c ON c.customer_id = cu.customer_id AND c.utility_id = NEW.utility_id
      JOIN utilities u   ON u.utility_id  = NEW.utility_id
     WHERE cu.area = NEW.area;

    INSERT INTO audit_log (action, details) VALUES ('Outage reported', 'Area: ' || NEW.area);
END;

-- T7: tell the customer whenever their complaint changes status.
CREATE TRIGGER trg_complaint_status
AFTER UPDATE OF status ON complaints
WHEN NEW.status <> OLD.status
BEGIN
    INSERT INTO notifications (user_id, title, message)
    SELECT cu.user_id, 'Complaint ' || NEW.complaint_no || ' updated',
           'Status changed to ' || REPLACE(NEW.status, '_', ' ') || '.'
      FROM customers cu WHERE cu.customer_id = NEW.customer_id;
END;

-- ---------------------------------------------------------------- views
-- One row per bill with customer and utility details and the amount still due.
CREATE VIEW v_bill_summary AS
SELECT b.bill_id, b.bill_no, b.billing_month, b.bill_date, b.due_date, b.units,
       b.total_amount, b.amount_paid, ROUND(b.total_amount - b.amount_paid, 2) AS outstanding,
       b.status, c.connection_id, c.connection_no, u.name AS utility, u.unit,
       cu.customer_id, cu.customer_code, cu.full_name AS customer_name, cu.area, cu.category
  FROM bills b
  JOIN connections c ON c.connection_id = b.connection_id
  JOIN utilities u   ON u.utility_id    = c.utility_id
  JOIN customers cu  ON cu.customer_id  = c.customer_id;

-- Unpaid bills whose due date has passed.
CREATE VIEW v_overdue_bills AS
SELECT s.*, CAST(julianday('now', 'localtime') - julianday(s.due_date) AS INTEGER) AS days_overdue
  FROM v_bill_summary s
 WHERE s.status <> 'paid' AND s.due_date < date('now', 'localtime');

-- Total units and billed amount per utility per month.
CREATE VIEW v_monthly_consumption AS
SELECT b.billing_month, u.name AS utility, u.unit,
       ROUND(SUM(b.units), 2) AS total_units, ROUND(SUM(b.total_amount), 2) AS total_billed
  FROM bills b
  JOIN connections c ON c.connection_id = b.connection_id
  JOIN utilities u   ON u.utility_id    = c.utility_id
 GROUP BY b.billing_month, u.name, u.unit;
