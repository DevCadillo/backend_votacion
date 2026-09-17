from datetime import datetime, timedelta

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app.auth import auth_bp
from app.extensions import db
from app.models import User, AuditLog


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Login exclusivo para administradores. Los votantes no usan esta
    pantalla: se identifican por nombre completo en /votar."""
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        identificador = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter(
            (User.usuario == identificador) | (User.correo == identificador)
        ).first()

        if not user or not user.check_password(password):
            flash("Usuario o contraseña incorrectos.", "danger")
            return render_template("auth/login.html")

        if user.estado != "activo":
            flash("Tu cuenta se encuentra inactiva. Contacta al administrador.", "danger")
            return render_template("auth/login.html")

        login_user(user)
        user.ultimo_acceso = datetime.utcnow()
        AuditLog.log("login", user_id=user.id, entidad="users", entidad_id=user.id,
                     detalle="Inicio de sesión de administrador", ip=request.remote_addr)
        db.session.commit()

        return redirect(url_for("admin.dashboard"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    AuditLog.log("logout", user_id=current_user.id, entidad="users", entidad_id=current_user.id,
                 detalle="Cierre de sesión", ip=request.remote_addr)
    db.session.commit()
    logout_user()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/recuperar-password", methods=["GET", "POST"])
def recuperar_password():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip()
        user = User.query.filter_by(correo=correo).first()
        if user:
            token = user.generate_reset_token()
            user.reset_expira = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            # En producción: enviar correo real con el enlace de reseteo.
            # url_for("auth.reset_password", token=token, _external=True)
        # Mensaje neutro por seguridad: no revela si el correo existe o no.
        flash("Si el correo existe en nuestro sistema, recibirás instrucciones para restablecer tu contraseña.", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/recuperar_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user:
        flash("El enlace de recuperación no es válido o ya expiró.", "danger")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        if not user.reset_expira or user.reset_expira < datetime.utcnow():
            user.reset_token = None
            user.reset_expira = None
            db.session.commit()
            flash("El enlace de recuperación ha expirado. Solicita uno nuevo.", "danger")
            return redirect(url_for("auth.login"))
        nueva_password = request.form.get("password")
        confirmar = request.form.get("password_confirm")
        if not nueva_password or nueva_password != confirmar:
            flash("Las contraseñas no coinciden.", "danger")
            return render_template("auth/reset_password.html", token=token)

        user.set_password(nueva_password)
        user.reset_token = None
        user.reset_expira = None
        db.session.commit()
        flash("Contraseña actualizada. Ya puedes iniciar sesión.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", token=token)
