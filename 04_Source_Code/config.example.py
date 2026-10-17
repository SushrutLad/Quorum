# Copy this file to config.py and change the values.
# config.py is ignored by git so real secrets never get committed.

# Any long random string. Generate one with:
#   python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = "change-me"

# Path of the SQLite database file (created by seed.py).
DATABASE = "eums.db"
