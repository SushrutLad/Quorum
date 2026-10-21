"""Packages the submission folders into Section_GroupNN_EnergyUtilityManagement_MidSem.zip

    python docs_src/make_zip.py A Group05
"""
import os
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDERS = ["01_Report", "02_Requirements", "03_Design", "04_Source_Code", "05_Testing",
           "06_Project_Management", "07_Demo"]
SKIP = ("__pycache__", ".pytest_cache", "eums.db", "config.py", ".pyc")

section = sys.argv[1] if len(sys.argv) > 1 else "X"
group = sys.argv[2] if len(sys.argv) > 2 else "GroupXX"
name = f"{section}_{group}_EnergyUtilityManagement_MidSem"

# The git history goes straight into the ZIP as contribution evidence
log = subprocess.run(["git", "log", "--date=short", "--pretty=format:%h %ad %an  %s"],
                     cwd=ROOT, capture_output=True, text=True).stdout

out = os.path.join(ROOT, name + ".zip")
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for folder in FOLDERS:
        for dirpath, dirnames, files in os.walk(os.path.join(ROOT, folder)):
            dirnames[:] = [d for d in dirnames if d not in SKIP]
            for file in files:
                if file.endswith(SKIP) or file in SKIP:
                    continue
                full = os.path.join(dirpath, file)
                z.write(full, os.path.join(name, os.path.relpath(full, ROOT)))
    z.write(os.path.join(ROOT, "README.md"), os.path.join(name, "README.md"))
    z.writestr(os.path.join(name, "06_Project_Management", "git_log.txt"), log + "\n")
print("Created", out)
