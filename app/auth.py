from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from app.extensions import db
from app.models import User

bp = Blueprint("auth", __name__, url_prefix="")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if not name or not email or len(password) < 6:
            flash("Please provide name, email, and a password of at least 6 characters.", "error")
            return render_template("register.html")
        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "error")
            return render_template("register.html")
        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Welcome! Your library is ready.", "success")
        return redirect(url_for("main.dashboard"))
    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        if user is None or not user.check_password(password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")
        login_user(user, remember=True)
        next_url = request.args.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("main.dashboard"))
    return render_template("login.html")


@bp.route("/logout")
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
