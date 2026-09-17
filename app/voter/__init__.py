from flask import Blueprint

voter_bp = Blueprint("voter", __name__, template_folder="../templates/voter")

from app.voter import routes  # noqa: E402,F401
