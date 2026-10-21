"""Log in as each role and save a screenshot of every page (used in the report).

Start the app first (python app.py), then run:  python docs_src/take_screenshots.py
"""
import os
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"
OUT = os.path.join(os.path.dirname(__file__), "screenshots")
CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def shot(page, name, url=None, full=False):
    if url:
        page.goto(BASE + url)
    page.wait_for_timeout(700)          # let charts finish animating
    page.screenshot(path=os.path.join(OUT, name + ".png"), full_page=full)


def login(page, user, pw):
    page.goto(BASE + "/logout")
    page.fill("#username", user)
    page.fill("#password", pw)
    page.click("button")


with sync_playwright() as p:
    kwargs = {"executable_path": CHROMIUM} if os.path.exists(CHROMIUM) else {}
    browser = p.chromium.launch(**kwargs)
    page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1.5)

    page.goto(BASE + "/login")
    shot(page, "01_login")

    login(page, "admin", "admin123")
    for name, url in [("02_admin_dashboard", "/staff/dashboard"), ("03_customers", "/staff/customers"),
                      ("04_customer_new", "/staff/customers/new"), ("05_connections", "/staff/connections"),
                      ("06_readings", "/staff/readings"), ("08_bills", "/staff/bills"),
                      ("10_payments", "/staff/payments"), ("11_complaints", "/staff/complaints"),
                      ("12_outages", "/staff/outages"), ("13_tariffs", "/staff/tariffs"),
                      ("14_employees", "/staff/employees"), ("15_reports", "/staff/reports")]:
        shot(page, name, url)

    # Meter reading entry by an employee, including the live validation message
    login(page, "reader", "reader123")
    page.goto(BASE + "/staff/readings/new")
    page.select_option("#meter_id", label="MTR-E-1001 - Sushrut Lad")
    page.wait_for_timeout(500)
    prev = float(page.input_value("#previous"))
    page.fill("#reading_value", f"{prev - 5:.1f}")
    shot(page, "07b_reading_invalid")
    page.fill("#reading_value", f"{prev + 170:.1f}")
    page.fill("#reading_date", (date.today() + timedelta(days=1)).isoformat())
    shot(page, "07_reading_form")
    page.click("#saveBtn")
    shot(page, "09_bill_generated", full=True)
    bill_url = page.url.replace(BASE, "").replace("/staff/", "/my/")

    login(page, "sushrut@example.com", "pass123")
    shot(page, "16_customer_dashboard", "/my/dashboard")
    shot(page, "17_customer_bills", "/my/bills")
    shot(page, "18_pay", bill_url + "/pay")
    page.click("text=Pay ")
    shot(page, "19_paid", full=True)
    for name, url in [("20_usage", "/my/usage"), ("21_my_complaints", "/my/complaints"),
                      ("22_my_outages", "/my/outages"), ("23_notifications", "/my/notifications"),
                      ("24_profile", "/my/profile"), ("25_my_connections", "/my/connections")]:
        shot(page, name, url)

    page.goto(BASE + "/staff/dashboard")
    shot(page, "26_customer_forbidden")
    browser.close()
print("Screenshots saved in", OUT)
