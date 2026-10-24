"""Builds every PDF in the submission folders from the HTML sections in docs_src/.

    1. Fill in docs_src/team.json (names, registration numbers, group, section)
    2. python docs_src/build_docs.py

Needs: pip install flask pytest playwright   (Jinja2 comes with Flask)
The test results in the report come from actually running pytest on 04_Source_Code.
"""
import json
import os
import re
import subprocess
import sys
from datetime import date

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CODE = os.path.join(ROOT, "04_Source_Code")
CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

# ------------------------------------------------------------------ test cases (also printed in Test_Cases.pdf)
TEST_CASES = [
    # id, pytest name, feature, input / steps, expected result
    ("UT-01", "test_ut01_two_slabs", "Slab billing",
     "250 kWh, residential electricity (0-100 @3.50, 100-300 @5.00), fixed 50, tax 5%",
     "Energy 1,100.00; tax 57.50; total 1,207.50"),
    ("UT-02", "test_ut02_zero_units_only_fixed_charge", "Slab billing", "0 units", "Only fixed + tax = 52.50, no slab rows"),
    ("UT-03", "test_ut03_exact_slab_boundary", "Slab billing", "Exactly 100 units (slab edge)",
     "Only first slab used; total 420.00"),
    ("UT-04", "test_ut04_open_ended_top_slab", "Slab billing", "400 units (reaches 300+ slab)",
     "Energy 2,050.00; total 2,205.00; 100 units in top slab"),
    ("UT-05", "test_ut05_negative_units_rejected", "Slab billing", "-5 units", "ValueError raised"),
    ("UT-06", "test_ut06_water_without_tax_and_decimal_units", "Slab billing", "15.5 kL water, no tax",
     "Energy 146.00; total 186.00"),
    ("IT-01", "test_it01_valid_login_goes_to_dashboard", "Login", "admin / admin123",
     "Redirect to /staff/dashboard; dashboard loads"),
    ("IT-02", "test_it02_wrong_password_rejected", "Login", "admin / wrong", "Stays on login with 'Invalid username or password'"),
    ("IT-03", "test_it03_not_logged_in_redirects_to_login", "Access control", "Open /staff/bills without logging in",
     "Redirect to /login"),
    ("IT-04", "test_it04_role_checks", "Access control (RBAC)",
     "Customer opens staff page; employee opens admin-only Tariffs", "HTTP 403 for both; employee can open Add Reading"),
    ("IT-05", "test_it05_customer_cannot_see_other_customers_bill", "Data isolation",
     "Sushrut (C1001) opens a bill that belongs to Sumit (C1002)", "HTTP 403 on bill and pay page"),
    ("IT-06", "test_it06_reading_to_bill_to_payment", "END-TO-END: reading -> bill -> payment",
     "Employee adds +250 kWh on Sushrut's meter; Sushrut pays 1,207.50 by UPI",
     "Bill of 1,207.50 created (unpaid); after payment status = paid and 'Payment received' notification"),
    ("IT-07", "test_it07_lower_reading_rejected", "Meter reading validation", "Current reading 10 below previous",
     "Trigger error 'Reading cannot be lower...'; no bill created"),
    ("IT-08", "test_it08_reading_date_must_move_forward", "Meter reading validation", "Reading date 2020-01-01",
     "Trigger error 'Reading date must be after...'"),
    ("IT-09", "test_it09_overpayment_rejected", "Payment validation", "Sushrut pays outstanding + 100",
     "Trigger error 'Payment exceeds outstanding balance'; bill not paid"),
    ("IT-10", "test_it10_partial_payment", "Counter payment", "Billing officer pays half the bill in cash",
     "Bill status = partial"),
    ("IT-11", "test_it11_outage_notifies_only_that_area", "Outage alerts", "Admin reports electricity outage in Alambagh",
     "Every Alambagh electricity customer notified; Hazratganj customers not notified"),
    ("IT-12", "test_it12_complaint_lifecycle", "Complaints", "Sushrut raises a complaint; technician marks it resolved",
     "Complaint visible to staff; status resolved with timestamp"),
    ("IT-13", "test_it13_duplicate_customer_email_rejected", "Customer registration", "Register Sushrut Lad again with the same email",
     "Error 'already exists'; customer count unchanged"),
    ("IT-14", "test_it14_tariff_change_does_not_alter_old_bills", "Tariff management", "Admin changes slab rate to 9.99",
     "New rate saved; old bill total unchanged"),
]


def run_tests():
    """Run pytest and return {test_name: 'PASS'|'FAIL'} plus the raw summary line."""
    out = subprocess.run([sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider"], cwd=CODE,
                         capture_output=True, text=True).stdout
    results = {m.group(1): "PASS" if m.group(2) == "PASSED" else "FAIL"
               for m in re.finditer(r"::(\w+) (PASSED|FAILED)", out)}
    summary = [line for line in out.splitlines() if " passed" in line or " failed" in line]
    with open(os.path.join(ROOT, "05_Testing", "Test_Evidence", "pytest_output.txt"), "w") as f:
        f.write(out)
    return results, (summary[-1].strip("= ") if summary else "tests did not run")


def count_loc():
    total = 0
    for folder, exts in [(CODE, (".py", ".sql")), (os.path.join(CODE, "templates"), (".html",)),
                         (os.path.join(CODE, "static", "css"), (".css",))]:
        for dirpath, _, files in os.walk(folder):
            if "tests" in dirpath or (folder == CODE and dirpath != CODE):
                continue
            for name in files:
                if name.endswith(exts):
                    with open(os.path.join(dirpath, name)) as f:
                        total += sum(1 for line in f if line.strip())
    with open(os.path.join(CODE, "static", "js", "charts.js")) as f:
        total += sum(1 for line in f if line.strip())
    return total


# ------------------------------------------------------------------ documents to build
REPORT = ["cover", "r_report"]

DOCS = [
    ("01_Report/MidSem_Project_Report.pdf", "Mid-Semester Project Report", REPORT),
    ("02_Requirements/SRS.pdf", "Software Requirements Specification", ["cover", "srs"]),
    ("02_Requirements/Use_Cases_or_User_Stories.pdf", "Use Cases and User Stories", ["cover", "s07_usecases"]),
    ("03_Design/Architecture_Diagram.pdf", "System Architecture", ["cover", "d_architecture"]),
    ("03_Design/Database_Design.pdf", "Database Design", ["cover", "d_database"]),
    ("03_Design/UML_Diagrams.pdf", "UML Diagrams", ["cover", "d_uml"]),
    ("03_Design/UI_Screens.pdf", "User Interface Screens", ["cover", "d_ui"]),
    ("05_Testing/Test_Cases.pdf", "Test Cases and Results", ["cover", "s11_testing"]),
    ("06_Project_Management/Project_Plan.pdf", "Project Plan", ["cover", "pm_plan"]),
    ("06_Project_Management/Contribution_Record.pdf", "Contribution Record", ["cover", "pm_contrib"]),
]


def main():
    with open(os.path.join(HERE, "team.json")) as f:
        team = json.load(f)
    results, summary = run_tests()
    loc = count_loc()
    kloc = 3.5                                      # estimated size of the finished system
    effort = 2.4 * kloc ** 1.05
    duration = 2.5 * effort ** 0.38

    env = Environment(loader=FileSystemLoader([os.path.join(HERE, "sections"), HERE]), autoescape=False)

    def svg(name):
        with open(os.path.join(HERE, "diagrams", name + ".svg")) as f:
            data = f.read()
        return re.sub(r"^<\?xml[^>]*>", "", data)

    def shot(name):
        return "file://" + os.path.join(HERE, "screenshots", name + ".png")

    context = dict(team=team, tests=TEST_CASES, results=results, summary=summary, loc=loc, kloc=kloc,
                   effort=effort, duration=duration, people=effort / duration, svg=svg, shot=shot,
                   today=date.today().strftime("%d %B %Y"))

    with sync_playwright() as p:
        kwargs = {"executable_path": CHROMIUM} if os.path.exists(CHROMIUM) else {}
        browser = p.chromium.launch(**kwargs)
        page = browser.new_page()
        for path, title, sections in DOCS:
            html = env.get_template("base.html").render(context, doc_title=title, sections=sections,
                                                        is_report=sections is REPORT)
            # Never split a table across pages, and keep a heading together with the table right below it
            html = re.sub(r"(<h([23])[^>]*>(?:(?!</h\2>).)*</h\2>\s*)(<table\b.*?</table>)",
                          r'<div class="keep">\1\3</div>', html, flags=re.S)
            tmp = os.path.join(HERE, "_build.html")
            with open(tmp, "w") as f:
                f.write(html)
            page.goto("file://" + tmp)
            page.wait_for_load_state("networkidle")
            out = os.path.join(ROOT, path)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            page.pdf(path=out, format="A4", print_background=True, display_header_footer=True,
                     header_template="<span></span>",
                     footer_template='<div style="font-size:8px;width:100%;padding:0 14mm;color:#64748b;text-align:right">'
                                     '<span class="pageNumber"></span> / <span class="totalPages"></span></div>',
                     margin={"top": "14mm", "bottom": "16mm", "left": "15mm", "right": "15mm"})
            print("built", path)
        browser.close()
    os.remove(os.path.join(HERE, "_build.html"))
    print(summary, "| LOC:", loc)


if __name__ == "__main__":
    main()
