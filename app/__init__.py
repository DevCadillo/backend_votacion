from flask import Flask, render_template

from config import Config
from app.extensions import db, login_manager, migrate
from app.csrf import csrf


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ---- Blueprints -----------------------------------------------------
    from app.auth import auth_bp
    from app.voter import voter_bp
    from app.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(voter_bp)
    app.register_blueprint(admin_bp)

    from flask import redirect, url_for, session, make_response
    from flask_login import current_user
    from app.voter.routes import get_voter_from_cookie

    @app.route("/")
    def index():
        # La pantalla principal del sistema es la de votación (sin login).
        # Los administradores entran por /login por separado.
        if current_user.is_authenticated and current_user.is_admin:
            return redirect(url_for("admin.dashboard"))
        if get_voter_from_cookie():
            return redirect(url_for("voter.home"))
        return redirect(url_for("voter.identificarse"))

    @app.route("/health")
    def health():
        return {"status": "ok"}, 200

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    # ---- Comandos CLI: flask seed-db ------------------------------------
    from app.seed import register_cli
    register_cli(app)

    return app
