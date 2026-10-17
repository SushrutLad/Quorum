"""Login check used by every page."""
from functools import wraps

from flask import abort, redirect, session, url_for


def login_required(*roles):
    """Decorator: user must be logged in, and (if roles are given) have one of them."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if roles and session["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator
