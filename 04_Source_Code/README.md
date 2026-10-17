# EUMS – Energy & Utility Management System

A web application for a utility office that supplies **electricity, water and gas**. It covers customers,
connections, meter readings, automatic slab-based billing, payments, complaints, outages, tariffs and reports. It has a
staff portal (admin and employees) and a customer self-service portal.

Built with **Python + Flask + SQLite + HTML templates**. Flask is the only package needed to run the app.

## Requirements

- Python 3.10 or newer (`python --version`)
- pip

## Run it (3 commands)

```bash
cd 04_Source_Code
pip install -r requirements.txt     # installs Flask and pytest
python seed.py                      # creates eums.db with demo data (deletes any old data)
python app.py                       # then open http://127.0.0.1:5000
```

On Windows, use `py` instead of `python` if `python` is not found.

### Demo logins

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `admin123` |
| Employee – meter reader | `reader` | `reader123` |
| Employee – billing officer | `billing` | `billing123` |
| Employee – technician | `tech` | `tech123` |
| Customer | `rahul@example.com` (or any email in `sample_data/customers.csv`) | `pass123` |

These are sample accounts with fictional data only.

## Try the end-to-end feature

1. Log in as `reader` and go to **Meter Readings → Add Reading**.
2. Pick meter `MTR-E-1001 - Rahul Verma`. The previous reading appears automatically.
3. Type a higher reading (a lower one is blocked), pick tomorrow's date and click **Save Reading**. The bill is generated.
4. Log out, log in as `rahul@example.com`, open **Bills & Payments**, click **Pay** and pay by UPI.
5. The bill becomes **Paid** and a notification appears.

## Configuration

Settings have safe defaults for running locally. To change them, copy the sample file:

```bash
cp config.example.py config.py      # Windows: copy config.example.py config.py
```

Then edit `SECRET_KEY` (and `DATABASE` if you want a different file). `config.py` is ignored by git, so no secrets are
committed.

## Database setup

`python seed.py` runs `schema.sql` (16 tables, 7 triggers, 3 views, 6 indexes) and loads demo data:
24 customers from `sample_data/customers.csv`, 59 connections, 6 months of readings with bills and payments, complaints
and outages. Run it again at any time to reset the data.

## Run the tests

```bash
python -m pytest -v
```

There are 20 tests: 6 unit tests for the billing formula (`tests/test_billing.py`) and 14 functional tests that use the
real app and a fresh database (`tests/test_app.py`).

## Folder structure

```
04_Source_Code/
├── app.py               # creates the Flask app, login/logout, template helpers
├── auth.py              # login_required(role) decorator
├── db.py                # SQLite connection per request
├── billing.py           # slab bill calculation + bill generation
├── routes_staff.py      # admin and employee pages
├── routes_customer.py   # customer portal pages
├── schema.sql           # tables, constraints, triggers, views, indexes
├── seed.py              # builds eums.db with demo data
├── config.example.py    # sample configuration
├── requirements.txt
├── sample_data/customers.csv
├── templates/           # one HTML page per feature (staff/ and portal/)
├── static/              # style.css, charts.js, Chart.js library
└── tests/               # pytest tests
```

## Slab billing formula

```
units in slab i = max(0, min(U, to_i) - from_i)
energy = sum(units in slab i * rate_i)
total  = (energy + fixed charge) * (1 + tax% / 100)
```

Example: 250 kWh on the domestic plan gives 100×3.50 + 150×5.00 = 1100, + 50 fixed = 1150, + 5% = **₹1,207.50**.
