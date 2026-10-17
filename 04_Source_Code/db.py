"""Small helpers for opening the SQLite database once per request."""
import sqlite3

from flask import current_app, g


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row          # rows behave like dicts: row["name"]
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, params=(), one=False):
    rows = get_db().execute(sql, params).fetchall()
    return (rows[0] if rows else None) if one else rows
