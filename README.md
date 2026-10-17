# EUMS – Energy & Utility Management System (SEPM Mid-Semester Submission)

Combined SEPM + DBMS course project, following the **Waterfall** model.

| Folder | Contents |
|---|---|
| `01_Report/` | `MidSem_Project_Report.pdf` – main report (all 16 required sections + appendices) |
| `02_Requirements/` | `SRS.pdf`, `Use_Cases_or_User_Stories.pdf` |
| `03_Design/` | Architecture, database design, UML diagrams, UI screens (PDF) and editable diagram sources |
| `04_Source_Code/` | Flask + SQLite application, README with run instructions, sample data, tests |
| `05_Testing/` | `Test_Cases.pdf` and `Test_Evidence/` (pytest log, screenshots) |
| `06_Project_Management/` | Project plan, meeting log, contribution record, git log |
| `07_Demo/` | `DEMO_VIDEO_LINK.txt` |
| `docs_src/` | Sources used to generate the PDFs (not needed for submission) |

## Before submitting

1. Fill in `docs_src/team.json` (group number, section, instructor, member names and registration numbers, video link).
2. Rebuild the PDFs: `pip install flask pytest playwright && python docs_src/build_docs.py`
3. Paste the video link into `07_Demo/DEMO_VIDEO_LINK.txt`.
4. Fill in the dates and attendees in the meeting log, and sign the contribution declaration.
5. Make the ZIP: `python docs_src/make_zip.py A Group05` → `A_Group05_EnergyUtilityManagement_MidSem.zip`
