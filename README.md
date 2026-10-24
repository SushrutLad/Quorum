# EUMS – Energy & Utility Management System

## How to run

You need **Python 3.10 or newer** (download it from python.org; on Windows, tick *"Add Python to PATH"* while installing).

```bash
cd 04_Source_Code
pip install -r requirements.txt
python seed.py
python app.py
```

Then open **http://127.0.0.1:5000** in your browser and log in:

| Who | Username | Password |
|---|---|---|
| Admin | `admin` | `admin123` |
| Employee (meter reader) | `reader` | `reader123` |
| Customer | `sushrut@example.com` | `pass123` |

**In VS Code:** File → Open Folder → pick `04_Source_Code`, open the terminal (Terminal → New Terminal) and run the
four commands above (skip the `cd` line).

- `seed.py` builds a fresh database with six months of sample data. Run it again whenever you want to reset the data.
- Stop the app with **Ctrl + C**. Next time, just run `python app.py`.
- Run the tests with `python -m pytest -v`. You should see **20 passed**.
- If `python` isn't found, try `py` (Windows) or `python3` (Mac). If port 5000 is busy (common on Mac), run
  `flask --app app run --port 5001` and open http://127.0.0.1:5001 instead.

---

**SEPM Mid-Semester Submission · CSEF · Group 3** · Team: Sumit P Surendran (20243590), Sreethan Reddy (20243550),
Sushrut Lad (20243551), Viswajith (20243559)

This is our SEPM project, which we're doing together with our DBMS project. It's a web app for a utility office that
handles electricity, water and gas: customers, meters, readings, automatic billing, payments, complaints and outages.
We followed the Waterfall model.

This README walks through each item on the mid-sem evaluation list and where to find it.

---

## 1. Where each requirement is

| Evaluation item | Where it is |
|---|---|
| Problem statement and objectives | Report, sections 1–2 |
| Stakeholders and scope | Report, sections 4–5 |
| Functional / non-functional requirements | Report, section 6, and `02_Requirements/SRS.pdf` |
| Prioritised requirements | Report, section 6 (MoSCoW column) |
| Use-case diagram / user stories | Report, section 7, and `02_Requirements/Use_Cases_or_User_Stories.pdf` |
| Architecture and database design | Report, section 8, and `03_Design/` |
| UI design / prototype | `03_Design/UI_Screens.pdf` (screenshots of every page) |
| A working end-to-end feature | Reading → bill → payment (see section 3 below) |
| Unit / functional testing | Report, section 11, and `05_Testing/` |
| Project plan and contribution record | Report, sections 12–13, and `06_Project_Management/` |
| Feasibility study (Waterfall) | Report, section 3 |

### Folder layout

```
01_Report/              MidSem_Project_Report.pdf   (main report)
02_Requirements/        SRS.pdf, Use_Cases_or_User_Stories.pdf
03_Design/              Architecture_Diagram.pdf, Database_Design.pdf, UML_Diagrams.pdf,
                        UI_Screens.pdf, diagram_sources/ (editable .mmd and .svg files)
04_Source_Code/         the app, its README, sample_data/, tests/
05_Testing/             Test_Cases.pdf, Test_Evidence/ (pytest log + screenshots)
06_Project_Management/  Project_Plan.pdf, Contribution_Record.pdf, git_log.txt
```

---

## 2. Showing the end-to-end feature

This is the part the evaluators most want to see working.

1. Log in as **reader / reader123**.
2. Go to **Meter Readings → Add Reading** and pick `MTR-E-1001 - Sushrut Lad`. The last reading fills in by itself.
3. Type a number *lower* than the last reading. You'll see the error and the Save button turns off. This shows the
   validation.
4. Now type a higher number, set the date to tomorrow, and click **Save Reading**. The bill is generated straight away,
   with the slab breakdown.
5. Log out and log in as **sushrut@example.com / pass123**. The new bill is on the dashboard.
6. Open **Bills & Payments → Pay**, choose UPI and pay. The bill turns **Paid** and a notification appears.
7. Optional: log in as **admin**, go to **Outages → Report Outage** for Teliyarganj, then log back in as Sushrut to see
   the alert.

---

## 3. Things still to fill in before uploading

- [ ] **AI-tool disclosure** – section 6 of the guidelines asks for this if any AI tool was used. Fill in the table
      in the report appendix.
- [ ] Check there are no passwords or keys anywhere. The only passwords are the sample demo logins above.

---

## 4. Rebuilding the PDFs and the ZIP

Only needed after you change `docs_src/team.json` or any text.

```bash
pip install flask pytest playwright
python -m playwright install chromium      # one time only
python docs_src/build_docs.py              # rebuilds every PDF and re-runs the tests
python docs_src/make_zip.py CSEF Group3
```

That creates `CSEF_Group3_EnergyUtilityManagement_MidSem.zip`, named the way the guidelines ask
(`Section_GroupNumber_ProjectTitle_MidSem.zip`). Open the ZIP once to check it before one of us uploads it to Moodle.

The report text lives in `docs_src/sections/` as HTML files if you want to edit wording.
