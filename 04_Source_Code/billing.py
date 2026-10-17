"""Bill calculation - kept separate from Flask so it is easy to unit test."""
from datetime import date, timedelta

DUE_DAYS = 15


def calculate_bill(units, slabs, fixed_charge, tax_percent):
    """Work out a bill using progressive (slab) pricing.

    slabs: list of (from_unit, to_unit, rate); to_unit None means "and above".
    Each slab charges only the units that fall inside it:
        units_in_slab = max(0, min(units, to_unit) - from_unit)
    """
    if units < 0:
        raise ValueError("Units cannot be negative")

    items = []
    energy_charge = 0.0
    for from_unit, to_unit, rate in sorted(slabs):
        upper = units if to_unit is None else min(units, to_unit)
        in_slab = max(0, upper - from_unit)
        if in_slab == 0:
            continue
        amount = round(in_slab * rate, 2)
        energy_charge += amount
        label = f"{from_unit:g}+" if to_unit is None else f"{from_unit:g}-{to_unit:g}"
        items.append({"description": f"Usage charge ({label} units)",
                      "units": in_slab, "rate": rate, "amount": amount})

    energy_charge = round(energy_charge, 2)
    tax = round((energy_charge + fixed_charge) * tax_percent / 100, 2)
    total = round(energy_charge + fixed_charge + tax, 2)
    return {"energy_charge": energy_charge, "fixed_charge": fixed_charge,
            "tax_amount": tax, "total_amount": total, "items": items}


def generate_bill(db, reading_id, bill_date=None):
    """Create the bill for one meter reading. Returns the new bill_id."""
    r = db.execute(
        """SELECT mr.reading_id, mr.consumption, mr.reading_date, c.connection_id, c.tariff_id,
                  t.fixed_charge, t.tax_percent
             FROM meter_readings mr
             JOIN meters m      ON m.meter_id = mr.meter_id
             JOIN connections c ON c.connection_id = m.connection_id
             JOIN tariff_plans t ON t.tariff_id = c.tariff_id
            WHERE mr.reading_id = ?""", (reading_id,)).fetchone()
    slabs = [(s["from_unit"], s["to_unit"], s["rate"]) for s in db.execute(
        "SELECT from_unit, to_unit, rate FROM tariff_slabs WHERE tariff_id = ?", (r["tariff_id"],))]

    calc = calculate_bill(r["consumption"], slabs, r["fixed_charge"], r["tax_percent"])

    bill_date = bill_date or date.fromisoformat(r["reading_date"])
    month = r["reading_date"][:7]
    count = db.execute("SELECT COUNT(*) FROM bills WHERE billing_month = ?", (month,)).fetchone()[0]
    bill_no = f"BILL{month.replace('-', '')}-{count + 1:04d}"

    cur = db.execute(
        """INSERT INTO bills (bill_no, connection_id, reading_id, billing_month, bill_date, due_date,
                              units, energy_charge, fixed_charge, tax_amount, total_amount)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (bill_no, r["connection_id"], reading_id, month, bill_date.isoformat(),
         (bill_date + timedelta(days=DUE_DAYS)).isoformat(), r["consumption"],
         calc["energy_charge"], calc["fixed_charge"], calc["tax_amount"], calc["total_amount"]))
    bill_id = cur.lastrowid

    rows = [(bill_id, i["description"], i["units"], i["rate"], i["amount"]) for i in calc["items"]]
    rows.append((bill_id, "Fixed charge", None, None, calc["fixed_charge"]))
    if calc["tax_amount"]:
        rows.append((bill_id, "Tax / duty", None, None, calc["tax_amount"]))
    db.executemany("INSERT INTO bill_items (bill_id, description, units, rate, amount) VALUES (?, ?, ?, ?, ?)", rows)
    return bill_id
