import secrets
from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, abort, make_response, current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.voter import voter_bp
from app.decorators import voter_session_required
from app.extensions import db
from app.models import Election, Category, Candidate, CandidateCategory, Vote, VoteReceipt, Voter, AuditLog, normalizar_nombre, normalizar_carnet

VOTER_COOKIE = "voter_session"
VOTER_COOKIE_MAX_AGE = 6 * 60 * 60


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="voter-session-v1")


def _set_voter_cookie(response, voter_id):
    token = _serializer().dumps({"voter_id": voter_id})
    response.set_cookie(VOTER_COOKIE, token, max_age=VOTER_COOKIE_MAX_AGE, httponly=True,
                        secure=bool(current_app.config.get("SESSION_COOKIE_SECURE", False)), samesite="Lax", path="/")
    return response


def _clear_voter_cookie(response):
    response.delete_cookie(VOTER_COOKIE, path="/")
    return response


def get_voter_from_cookie():
    token = request.cookies.get(VOTER_COOKIE)
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=VOTER_COOKIE_MAX_AGE)
        voter_id = int(data.get("voter_id"))
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return None
    return Voter.query.get(voter_id)


def _eleccion_activa():
    return Election.query.filter_by(estado="activa").order_by(Election.fecha_inicio.desc()).first()


def _categorias_con_estado(election, voter):
    votadas_ids = {r.category_id for r in VoteReceipt.query.filter_by(voter_id=voter.id, election_id=election.id).all()}
    resultado = []
    for cat in Category.query.filter_by(election_id=election.id).order_by(Category.orden).all():
        if cat.estado != "activa":
            estado = "no_disponible"
        elif cat.id in votadas_ids:
            estado = "votado"
        else:
            estado = "pendiente"
        resultado.append({"categoria": cat, "estado": estado, "n_candidatos": len([c for c in cat.candidatos if c.estado == "activo"])})
    return resultado, votadas_ids


@voter_bp.route("/votar", methods=["GET", "POST"])
def identificarse():
    voter = get_voter_from_cookie()
    if voter and voter.estado == "activo":
        return redirect(url_for("voter.home"))

    if request.method == "POST":
        codigo = normalizar_carnet(request.form.get("carnet", ""))
        if not codigo:
            flash("Ingresa tu número de carnet de identidad.", "warning")
            return render_template("voter/identificarse.html", carnet=codigo)

        voter = Voter.query.filter_by(codigo_padron=codigo).first()
        if not voter:
            return render_template("voter/confirmar_registro.html", codigo=codigo)
        if voter.estado != "activo":
            flash("Tu registro como votante se encuentra inactivo. Contacta al administrador.", "danger")
            return render_template("voter/identificarse.html", carnet=codigo)

        AuditLog.log("identificacion_votante", voter_id=voter.id, entidad="voters", entidad_id=voter.id,
                     detalle="Identificación para votar", ip=request.remote_addr)
        db.session.commit()
        return _set_voter_cookie(redirect(url_for("voter.home")), voter.id)

    return render_template("voter/identificarse.html", carnet="")


@voter_bp.route("/votar/registrarse", methods=["POST"])
def registrarse():
    nombre = normalizar_nombre(request.form.get("nombre_completo", ""))
    codigo = normalizar_carnet(request.form.get("codigo_padron", ""))

    if not codigo:
        flash("Ingresa tu número de carnet de identidad.", "warning")
        return redirect(url_for("voter.identificarse"))
    if len(nombre.split()) < 2:
        flash("Ingresa tu nombre completo (nombre y apellido).", "warning")
        return render_template("voter/confirmar_registro.html", codigo=codigo)

    existente = Voter.query.filter(
        (db.func.lower(Voter.nombre_completo) == nombre.lower()) | (Voter.codigo_padron == codigo)
    ).first()
    if existente:
        flash("Ese nombre o código de padrón ya está registrado.", "danger")
        return redirect(url_for("voter.identificarse"))

    voter = Voter(nombre_completo=nombre, codigo_padron=codigo, estado="activo")
    db.session.add(voter)
    db.session.flush()
    AuditLog.log("autoregistro_votante", voter_id=voter.id, entidad="voters", entidad_id=voter.id,
                 detalle="Autoregistro de votante desde /votar", ip=request.remote_addr)
    db.session.commit()

    return _set_voter_cookie(redirect(url_for("voter.home")), voter.id)


@voter_bp.route("/votar/salir")
def salir():
    return _clear_voter_cookie(redirect(url_for("voter.identificarse")))


@voter_bp.route("/votacion")
@voter_session_required
def home(voter):
    election = _eleccion_activa()
    if not election:
        return render_template("voter/sin_eleccion.html", voter=voter)
    categorias, votadas_ids = _categorias_con_estado(election, voter)
    total = len(categorias)
    progreso = round((len(votadas_ids) / total) * 100) if total else 0
    return render_template("voter/home.html", voter=voter, election=election, categorias=categorias,
                           progreso=progreso, completadas=len(votadas_ids), total=total)


@voter_bp.route("/votacion/categoria/<int:category_id>")
@voter_session_required
def ver_categoria(category_id, voter):
    category = Category.query.get_or_404(category_id)
    election = category.election
    if not election.puede_votar():
        flash("Esta elección no está disponible para votar en este momento.", "warning")
        return redirect(url_for("voter.home"))
    if category.estado != "activa":
        flash("Esta categoría no está disponible.", "warning")
        return redirect(url_for("voter.home"))
    if VoteReceipt.query.filter_by(voter_id=voter.id, election_id=election.id, category_id=category.id).first():
        flash("Ya emitiste tu voto para esta categoría.", "info")
        return redirect(url_for("voter.home"))
    candidatos = [c for c in category.candidatos if c.estado == "activo"]
    return render_template("voter/categoria.html", voter=voter, category=category, candidatos=candidatos)


@voter_bp.route("/votacion/categoria/<int:category_id>/revisar", methods=["POST"])
@voter_session_required
def revisar_voto(category_id, voter):
    category = Category.query.get_or_404(category_id)
    election = category.election
    if not election.puede_votar() or category.estado != "activa":
        abort(400, "La categoría no está disponible para votar.")
    if VoteReceipt.query.filter_by(voter_id=voter.id, election_id=election.id, category_id=category.id).first():
        flash("Ya emitiste tu voto para esta categoría.", "info")
        return redirect(url_for("voter.home"))
    ids = request.form.getlist("candidato_id")
    try:
        ids = list(dict.fromkeys(int(x) for x in ids))
    except ValueError:
        abort(400, "Selección inválida.")
    if not ids or len(ids) > category.max_selecciones:
        abort(400, f"Debes seleccionar entre 1 y {category.max_selecciones} candidato(s).")
    candidatos = Candidate.query.filter(Candidate.id.in_(ids), Candidate.estado == "activo").all()
    if len(candidatos) != len(ids):
        abort(400, "Uno o más candidatos no son válidos.")
    valid_ids = {x.candidate_id for x in CandidateCategory.query.filter(CandidateCategory.category_id == category.id, CandidateCategory.candidate_id.in_(ids)).all()}
    if valid_ids != set(ids):
        abort(400, "Uno o más candidatos no pertenecen a esta categoría.")
    return render_template("voter/confirmar.html", voter=voter, category=category, candidatos=candidatos)


@voter_bp.route("/votacion/categoria/<int:category_id>/confirmar", methods=["POST"])
@voter_session_required
def confirmar_voto(category_id, voter):
    category = Category.query.get_or_404(category_id)
    election = category.election
    if not election.puede_votar() or category.estado != "activa":
        flash("La elección o categoría ya no admite votos.", "danger")
        return redirect(url_for("voter.home"))
    if VoteReceipt.query.filter_by(voter_id=voter.id, election_id=election.id, category_id=category.id).first():
        flash("Ya registraste tu voto en esta categoría; no puede modificarse.", "warning")
        return redirect(url_for("voter.home"))
    ids = request.form.getlist("candidato_id")
    try:
        ids = list(dict.fromkeys(int(x) for x in ids))
    except ValueError:
        abort(400, "Selección inválida.")
    if not ids or len(ids) > category.max_selecciones:
        abort(400, f"Debes seleccionar entre 1 y {category.max_selecciones} candidato(s).")
    candidatos = Candidate.query.filter(Candidate.id.in_(ids), Candidate.estado == "activo").all()
    if len(candidatos) != len(ids):
        abort(400, "Uno o más candidatos no son válidos.")
    valid_ids = {x.candidate_id for x in CandidateCategory.query.filter(CandidateCategory.category_id == category.id, CandidateCategory.candidate_id.in_(ids)).all()}
    if valid_ids != set(ids):
        abort(400, "Uno o más candidatos no pertenecen a esta categoría.")
    try:
        for candidato in candidatos:
            db.session.add(Vote(election_id=election.id, category_id=category.id, candidate_id=candidato.id,
                                voter_id=None if election.secreta else voter.id))
        db.session.add(VoteReceipt(voter_id=voter.id, category_id=category.id, election_id=election.id,
                                   codigo_comprobante=secrets.token_hex(16)))
        voter.iniciado = True
        AuditLog.log("emitir_voto", voter_id=voter.id, entidad="categories", entidad_id=category.id,
                     detalle=f"Voto registrado en categoría {category.nombre}", ip=request.remote_addr)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("No se pudo registrar el voto. Es posible que ya haya sido registrado.", "danger")
        return redirect(url_for("voter.home"))
    return render_template("voter/exito.html", voter=voter, category=category)


@voter_bp.route("/votacion/resumen")
@voter_session_required
def resumen(voter):
    election = _eleccion_activa()
    if not election:
        return redirect(url_for("voter.home"))
    categorias, votadas_ids = _categorias_con_estado(election, voter)
    total = len(categorias)
    progreso = round((len(votadas_ids) / total) * 100) if total else 0
    completas = [c for c in categorias if c["estado"] == "votado"]
    pendientes = [c for c in categorias if c["estado"] == "pendiente"]
    return render_template("voter/resumen.html", voter=voter, election=election, progreso=progreso,
                           completas=completas, pendientes=pendientes, total=total)


@voter_bp.route("/votacion/finalizar", methods=["POST"])
@voter_session_required
def finalizar(voter):
    election = _eleccion_activa()
    if not election or not election.puede_votar():
        flash("La elección ya no está disponible.", "warning")
        return redirect(url_for("voter.home"))
    obligatorias = Category.query.filter_by(election_id=election.id, estado="activa", obligatoria=True).all()
    votadas_ids = {r.category_id for r in VoteReceipt.query.filter_by(voter_id=voter.id, election_id=election.id).all()}
    faltantes = [c for c in obligatorias if c.id not in votadas_ids]
    if faltantes:
        flash("Aún tienes categorías obligatorias pendientes por votar.", "warning")
        return redirect(url_for("voter.resumen"))
    voter.terminado = True
    voter.terminado_at = datetime.utcnow()
    AuditLog.log("finalizar_votacion", voter_id=voter.id, entidad="voters", entidad_id=voter.id,
                 detalle=f"Finalizó la elección {election.nombre}", ip=request.remote_addr)
    db.session.commit()
    return render_template("voter/finalizado.html", voter=voter, election=election)


@voter_bp.route("/perfil")
@voter_session_required
def perfil(voter):
    return render_template("voter/perfil.html", voter=voter)
