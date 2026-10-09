"""
pages.py - Routes that return HTML pages (not JSON).
"""
import hmac

from flask import Blueprint, redirect, render_template, request, session, url_for

from config import Config

pages = Blueprint("pages", __name__)


@pages.route("/")
def home():
    return render_template("index.html")
@pages.route("/analytics")
def analytics_page():
    return render_template("analytics.html")


@pages.route("/staff")
def staff_panel():
    if not session.get("is_staff"):
        return redirect(url_for("pages.staff_login"))
    return render_template("staff.html")


@pages.route("/staff/login", methods=["GET", "POST"])
def staff_login():
    error = None
    if request.method == "POST":
        pin = request.form.get("pin", "")
        if hmac.compare_digest(pin, Config.STAFF_PIN):   # safe comparison
            session["is_staff"] = True
            return redirect(url_for("pages.staff_panel"))
        error = "Incorrect PIN. Try again."
    return render_template("staff_login.html", error=error)


@pages.route("/staff/logout")
def staff_logout():
    session.pop("is_staff", None)
    return redirect(url_for("pages.home"))