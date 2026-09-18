import os
import uuid
import requests
from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.admin import admin_bp
from app.decorators import admin_required, permission_required, superadmin_required
from app.extensions import db
from app.models import (
    Election, Category, Candidate, CandidateCategory, Voter,
    Vote, VoteReceipt, AuditLog, User, Admin, normalizar_nombre, normalizar_carnet,
)

EXTENSIONES_PERMITIDAS = {"png", "jpg", "jpeg", "webp"}

# Categorías estándar para un concurso tipo "Mister y Miss" con categorías
# especiales, además de las dos principales. Se pueden crear todas de una vez
# desde /admin/categorias con el botón "Crear categorías estándar".
CATEGORIAS_ESTANDAR = [
    "Miss", "Mister", "Puntualidad", "Alegre", "Creativo", "Conocimiento",
    "Deportes/Competitivo", "Comelón", "Sociable", "Influencer", "Servicio", "Adoración",
]


def _eleccion_con_votos(election_id):
    return db.session.query(Vote.id).filter(Vote.election_id == election_id).first() is not None


def _votos_categoria(category_id):
    return db.session.query(Vote.id).filter(Vote.category_id == category_id).first() is not None


def _votos_candidato(candidate_id):
    return db.session.query(Vote.id).filter(Vote.candidate_id == candidate_id).first() is not None


def _categorias_con_voto_por_candidato(candidate_id):
    """Categorías donde ESE candidato específico ya tiene votos registrados
    (no se le pueden quitar esas categorías sin romper la integridad electoral)."""
    return {cid for (cid,) in db.session.query(Vote.category_id)
            .filter(Vote.candidate_id == candidate_id).distinct()}


def _extension_valida(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in EXTENSIONES_PERMITIDAS


def _guardar_foto_candidato(archivo, candidate_id):
    """Guarda una foto en Supabase Storage en producción o localmente en desarrollo."""
    if not archivo or not archivo.filename or not _extension_valida(archivo.filename):
        return None

    ext = secure_filename(archivo.filename).rsplit(".", 1)[1].lower()
    nombre_archivo = f"cand_{candidate_id}_{uuid.uuid4().hex[:8]}.{ext}"

    supabase_url = current_app.config.get("SUPABASE_URL")
    service_key = current_app.config.get("SUPABASE_SERVICE_ROLE_KEY")
    bucket = current_app.config.get("SUPABASE_STORAGE_BUCKET", "candidatos")

    if supabase_url and service_key:
        contenido = archivo.read()
        content_type = archivo.mimetype or "application/octet-stream"
        endpoint = f"{supabase_url}/storage/v1/object/{bucket}/{nombre_archivo}"
        r = requests.post(endpoint, data=contenido, headers={
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "Content-Type": content_type,
            "x-upsert": "false",
        }, timeout=30)
        if not r.ok:
            current_app.logger.error("Error subiendo foto a Supabase Storage: %s", r.text)
            return None
        return f"{supabase_url}/storage/v1/object/public/{bucket}/{nombre_archivo}"

    carpeta = os.path.join(current_app.root_path, "static", "uploads", "candidatos")
    os.makedirs(carpeta, exist_ok=True)
    ruta_absoluta = os.path.join(carpeta, nombre_archivo)
    archivo.save(ruta_absoluta)
    return f"/static/uploads/candidatos/{nombre_archivo}"


def _eliminar_foto_si_existe(foto_url):
    if not foto_url:
        return

    supabase_url = current_app.config.get("SUPABASE_URL")
    service_key = current_app.config.get("SUPABASE_SERVICE_ROLE_KEY")
    bucket = current_app.config.get("SUPABASE_STORAGE_BUCKET", "candidatos")
    public_prefix = f"{supabase_url}/storage/v1/object/public/{bucket}/" if supabase_url else ""

    if public_prefix and foto_url.startswith(public_prefix) and service_key:
        nombre_archivo = foto_url[len(public_prefix):]
        endpoint = f"{supabase_url}/storage/v1/object/{bucket}/{nombre_archivo}"
        r = requests.delete(endpoint, headers={
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
        }, timeout=30)
        if not r.ok:
            current_app.logger.warning("No se pudo eliminar foto de Supabase Storage: %s", r.text)
        return

    if foto_url.startswith("/static/"):
        ruta = os.path.join(current_app.root_path, *foto_url.lstrip("/").split("/"))
        if os.path.exists(ruta):
            try:
                os.remove(ruta)
            except OSError:
                pass


@admin_bp.route("/")
@login_required
@admin_required
def dashboard():
    election = Election.query.order_by(Election.fecha_inicio.desc()).first()
    total_votantes = Voter.query.count()
    if election:
        iniciaron = db.session.query(VoteReceipt.voter_id).filter(VoteReceipt.election_id == election.id).distinct().count()
        total_recibos = db.session.query(VoteReceipt.voter_id).filter(VoteReceipt.election_id == election.id).distinct().count()
        completaron = total_recibos
    else:
        iniciaron = completaron = 0
    total_categorias = Category.query.filter_by(election_id=election.id).count() if election else 0
    total_candidatos = Candidate.query.count()
    participacion = round((iniciaron / total_votantes) * 100) if total_votantes else 0

    return render_template(
        "admin/dashboard.html",
        election=election, total_votantes=total_votantes, iniciaron=iniciaron,
        completaron=completaron, total_categorias=total_categorias,
        total_candidatos=total_candidatos, participacion=participacion,
    )


# ---------------------------------------------------------------- ELECCIONES
@admin_bp.route("/elecciones")
@login_required
@admin_required
@permission_required("elecciones")
def elecciones():
    lista = Election.query.order_by(Election.fecha_inicio.desc()).all()
    return render_template("admin/elecciones.html", elecciones=lista)


@admin_bp.route("/elecciones/nueva", methods=["GET", "POST"])
@login_required
@admin_required
@permission_required("elecciones")
def nueva_eleccion():
    if request.method == "POST":
        try:
            inicio = datetime.fromisoformat(request.form["fecha_inicio"])
            fin = datetime.fromisoformat(request.form["fecha_fin"])
        except (KeyError, ValueError):
            flash("Las fechas de la elección no son válidas.", "danger")
            return render_template("admin/eleccion_form.html", eleccion=None)
        if inicio >= fin:
            flash("La fecha de inicio debe ser anterior a la fecha de finalización.", "danger")
            return render_template("admin/eleccion_form.html", eleccion=None)
        e = Election(
            nombre=request.form.get("nombre", "").strip(),
            descripcion=request.form.get("descripcion"),
            institucion=request.form.get("institucion"),
            fecha_inicio=inicio, fecha_fin=fin,
            resultados_publicos=bool(request.form.get("resultados_publicos")),
            secreta=bool(request.form.get("secreta")),
            estado="proxima", created_by=current_user.id,
        )
        if not e.nombre:
            flash("El nombre de la elección es obligatorio.", "danger")
            return render_template("admin/eleccion_form.html", eleccion=None)
        db.session.add(e)
        db.session.flush()
        AuditLog.log("crear_eleccion", user_id=current_user.id, entidad="elections",
                     entidad_id=e.id, detalle=e.nombre, ip=request.remote_addr)
        db.session.commit()
        flash("Elección creada correctamente.", "success")
        return redirect(url_for("admin.elecciones"))
    return render_template("admin/eleccion_form.html", eleccion=None)


@admin_bp.route("/elecciones/<int:election_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
@permission_required("elecciones")
def editar_eleccion(election_id):
    e = Election.query.get_or_404(election_id)
    if request.method == "POST":
        try:
            inicio = datetime.fromisoformat(request.form["fecha_inicio"])
            fin = datetime.fromisoformat(request.form["fecha_fin"])
        except (KeyError, ValueError):
            flash("Las fechas no son válidas.", "danger")
            return render_template("admin/eleccion_form.html", eleccion=e)
        if inicio >= fin:
            flash("La fecha de inicio debe ser anterior a la finalización.", "danger")
            return render_template("admin/eleccion_form.html", eleccion=e)
        tiene_votos = _eleccion_con_votos(e.id)
        e.nombre = request.form.get("nombre", "").strip()
        e.descripcion = request.form.get("descripcion")
        e.institucion = request.form.get("institucion")
        if tiene_votos and (inicio != e.fecha_inicio or fin != e.fecha_fin):
            flash("Las fechas no pueden modificarse porque la elección ya tiene votos.", "danger")
            return render_template("admin/eleccion_form.html", eleccion=e)
        e.fecha_inicio, e.fecha_fin = inicio, fin
        e.resultados_publicos = bool(request.form.get("resultados_publicos"))
        if not tiene_votos:
            e.secreta = bool(request.form.get("secreta"))
        else:
            flash("La modalidad secreta no puede cambiarse porque la elección ya tiene votos.", "warning")
        db.session.commit()
        flash("Elección actualizada.", "success")
        return redirect(url_for("admin.elecciones"))
    return render_template("admin/eleccion_form.html", eleccion=e)

@admin_bp.route("/elecciones/<int:election_id>/estado", methods=["POST"])
@login_required
@admin_required
@permission_required("elecciones")
def cambiar_estado_eleccion(election_id):
    e = Election.query.get_or_404(election_id)
    nuevo = request.form.get("estado")
    if nuevo not in ("proxima", "activa", "finalizada"):
        flash("Estado no válido.", "danger")
        return redirect(url_for("admin.elecciones"))
    if nuevo == "activa":
        otra = Election.query.filter(Election.id != e.id, Election.estado == "activa").first()
        if otra:
            flash(f"No puedes activar esta elección porque '{otra.nombre}' ya está activa.", "danger")
            return redirect(url_for("admin.elecciones"))
        if e.estado == "finalizada":
            flash("Una elección finalizada no puede volver a activarse.", "danger")
            return redirect(url_for("admin.elecciones"))
        if not e.categories:
            flash("No puedes activar una elección sin categorías.", "danger")
            return redirect(url_for("admin.elecciones"))
    e.estado = nuevo
    AuditLog.log("cambiar_estado_eleccion", user_id=current_user.id, entidad="elections",
                 entidad_id=e.id, detalle=nuevo, ip=request.remote_addr)
    db.session.commit()
    flash(f"Estado de la elección actualizado a '{nuevo}'.", "success")
    return redirect(url_for("admin.elecciones"))

# --------------------------------------------------------------- CATEGORÍAS
@admin_bp.route("/categorias")
@login_required
@admin_required
@permission_required("categorias")
def categorias():
    election = Election.query.order_by(Election.fecha_inicio.desc()).first()
    lista = Category.query.filter_by(election_id=election.id).order_by(Category.orden).all() if election else []
    return render_template("admin/categorias.html", categorias=lista, election=election)


@admin_bp.route("/categorias/nueva", methods=["POST"])
@login_required
@admin_required
@permission_required("categorias")
def nueva_categoria():
    election = Election.query.order_by(Election.fecha_inicio.desc()).first()
    if not election:
        flash("Primero crea una elección.", "danger")
        return redirect(url_for("admin.categorias"))
    orden_max = db.session.query(db.func.max(Category.orden)).filter_by(election_id=election.id).scalar() or 0
    c = Category(
        election_id=election.id,
        nombre=request.form["nombre"],
        descripcion=request.form.get("descripcion"),
        max_selecciones=int(request.form.get("max_selecciones", 1)),
        obligatoria=bool(request.form.get("obligatoria")),
        orden=orden_max + 1,
    )
    db.session.add(c)
    db.session.commit()
    flash("Categoría creada.", "success")
    return redirect(url_for("admin.categorias"))


@admin_bp.route("/categorias/estandar", methods=["POST"])
@login_required
@admin_required
@permission_required("categorias")
def crear_categorias_estandar():
    """Crea de una sola vez las categorías estándar (Miss, Mister y las
    categorías especiales) que aún no existan en la elección actual."""
    election = Election.query.order_by(Election.fecha_inicio.desc()).first()
    if not election:
        flash("Primero crea una elección.", "danger")
        return redirect(url_for("admin.categorias"))

    existentes = {c.nombre.strip().lower() for c in Category.query.filter_by(election_id=election.id).all()}
    orden_max = db.session.query(db.func.max(Category.orden)).filter_by(election_id=election.id).scalar() or 0

    creadas = 0
    for nombre in CATEGORIAS_ESTANDAR:
        if nombre.strip().lower() in existentes:
            continue
        orden_max += 1
        db.session.add(Category(election_id=election.id, nombre=nombre, max_selecciones=1,
                                 obligatoria=True, orden=orden_max))
        creadas += 1

    db.session.commit()
    if creadas:
        flash(f"Se crearon {creadas} categoría(s) estándar. Ahora puedes asignarlas a cada candidato "
              "desde 'Candidatos'.", "success")
    else:
        flash("Las categorías estándar ya existían en esta elección.", "info")
    return redirect(url_for("admin.categorias"))


@admin_bp.route("/categorias/<int:category_id>/editar", methods=["POST"])
@login_required
@admin_required
@permission_required("categorias")
def editar_categoria(category_id):
    c = Category.query.get_or_404(category_id)
    try:
        max_sel = int(request.form.get("max_selecciones", 1))
    except ValueError:
        max_sel = 1
    if max_sel < 1:
        flash("El número máximo de selecciones debe ser al menos 1.", "danger")
        return redirect(url_for("admin.categorias"))
    c.nombre = request.form.get("nombre", "").strip()
    c.descripcion = request.form.get("descripcion")
    if _votos_categoria(c.id) and (max_sel != c.max_selecciones or bool(request.form.get("obligatoria")) != bool(c.obligatoria)):
        flash("No se puede cambiar el número de selecciones ni la obligatoriedad de una categoría que ya tiene votos.", "warning")
        return redirect(url_for("admin.categorias"))
    c.max_selecciones = max_sel
    c.obligatoria = bool(request.form.get("obligatoria"))
    db.session.commit()
    flash("Categoría actualizada.", "success")
    return redirect(url_for("admin.categorias"))


@admin_bp.route("/categorias/<int:category_id>/eliminar", methods=["POST"])
@login_required
@admin_required
@permission_required("categorias")
def eliminar_categoria(category_id):
    c = Category.query.get_or_404(category_id)
    if _votos_categoria(c.id):
        flash("No se puede eliminar una categoría que ya tiene votos. Puedes desactivarla.", "danger")
        return redirect(url_for("admin.categorias"))
    db.session.delete(c)
    db.session.commit()
    flash("Categoría eliminada.", "info")
    return redirect(url_for("admin.categorias"))


@admin_bp.route("/categorias/<int:category_id>/toggle", methods=["POST"])
@login_required
@admin_required
@permission_required("categorias")
def toggle_categoria(category_id):
    c = Category.query.get_or_404(category_id)
    # El estado controla visibilidad futura; los votos históricos se conservan intactos.
    c.estado = "inactiva" if c.estado == "activa" else "activa"
    AuditLog.log("cambiar_estado_categoria", user_id=current_user.id, entidad="categories", entidad_id=c.id, detalle=c.estado, ip=request.remote_addr)
    db.session.commit()
    return redirect(url_for("admin.categorias"))


@admin_bp.route("/categorias/<int:category_id>/mover/<direccion>", methods=["POST"])
@login_required
@admin_required
@permission_required("categorias")
def mover_categoria(category_id, direccion):
    c = Category.query.get_or_404(category_id)
    vecino_query = Category.query.filter_by(election_id=c.election_id)
    vecino = (
        vecino_query.filter(Category.orden < c.orden).order_by(Category.orden.desc()).first()
        if direccion == "arriba"
        else vecino_query.filter(Category.orden > c.orden).order_by(Category.orden.asc()).first()
    )
    if vecino:
        c.orden, vecino.orden = vecino.orden, c.orden
        db.session.commit()
    return redirect(url_for("admin.categorias"))


# --------------------------------------------------------------- CANDIDATOS
@admin_bp.route("/candidatos")
@login_required
@admin_required
@permission_required("candidatos")
def candidatos():
    election = Election.query.order_by(Election.fecha_inicio.desc()).first()
    categorias_disp = Category.query.filter_by(election_id=election.id).order_by(Category.orden).all() if election else []
    lista = Candidate.query.order_by(Candidate.nombre).all()
    ids_con_votos = {cid for (cid,) in db.session.query(Vote.candidate_id).distinct()}
    votos_por_candidato_categoria = {}
    for cid, catid in db.session.query(Vote.candidate_id, Vote.category_id).distinct():
        votos_por_candidato_categoria.setdefault(cid, set()).add(catid)
    return render_template("admin/candidatos.html", candidatos=lista, categorias=categorias_disp,
                           ids_con_votos=ids_con_votos,
                           votos_por_candidato_categoria=votos_por_candidato_categoria)


@admin_bp.route("/candidatos/nuevo", methods=["POST"])
@login_required
@admin_required
@permission_required("candidatos")
def nuevo_candidato():
    nombre = request.form.get("nombre", "").strip()
    election_actual = Election.query.order_by(Election.fecha_inicio.desc()).first()
    categoria_ids = set(request.form.getlist("categoria_ids", type=int))
    categorias_validas = (
        Category.query.filter(Category.id.in_(categoria_ids), Category.election_id == election_actual.id).all()
        if election_actual and categoria_ids else []
    )
    if not nombre:
        flash("El nombre del candidato es obligatorio.", "danger")
        return redirect(url_for("admin.candidatos"))
    if not election_actual or len(categorias_validas) != len(categoria_ids):
        flash("Selecciona al menos una categoría válida de la elección actual.", "danger")
        return redirect(url_for("admin.candidatos"))

    c = Candidate(
        nombre=nombre,
        numero_lista=request.form.get("numero_lista"),
        agrupacion=request.form.get("agrupacion"),
        propuesta=request.form.get("propuesta"),
    )
    db.session.add(c)
    db.session.flush()  # para obtener c.id antes de guardar la foto y hacer commit

    for categoria in categorias_validas:
        db.session.add(CandidateCategory(candidate_id=c.id, category_id=categoria.id))

    foto_url = _guardar_foto_candidato(request.files.get("foto"), c.id)
    if foto_url:
        c.foto_url = foto_url

    AuditLog.log("crear_candidato", user_id=current_user.id, entidad="candidates",
                 entidad_id=c.id, detalle=c.nombre, ip=request.remote_addr)
    db.session.commit()
    flash(f"Candidato registrado en {len(categorias_validas)} categoría(s).", "success")
    return redirect(url_for("admin.candidatos"))


@admin_bp.route("/candidatos/<int:candidate_id>/editar", methods=["POST"])
@login_required
@admin_required
@permission_required("candidatos")
def editar_candidato(candidate_id):
    c = Candidate.query.get_or_404(candidate_id)
    nombre = request.form.get("nombre", "").strip()
    numero_lista = request.form.get("numero_lista")
    categoria_ids = set(request.form.getlist("categoria_ids", type=int))
    if not nombre or not categoria_ids:
        flash("Nombre y al menos una categoría son obligatorios.", "danger")
        return redirect(url_for("admin.candidatos"))

    election_actual = Election.query.order_by(Election.fecha_inicio.desc()).first()
    categorias_validas = (
        Category.query.filter(Category.id.in_(categoria_ids), Category.election_id == election_actual.id).all()
        if election_actual else []
    )
    if not election_actual or len(categorias_validas) != len(categoria_ids):
        flash("Una o más categorías seleccionadas no pertenecen a la elección actual.", "danger")
        return redirect(url_for("admin.candidatos"))

    tiene_votos = _votos_candidato(c.id)
    cambia_datos_electorales = tiene_votos and (nombre != c.nombre or numero_lista != c.numero_lista)

    # Campos que siempre se pueden actualizar, tenga votos o no el candidato.
    c.agrupacion = request.form.get("agrupacion")
    c.propuesta = request.form.get("propuesta")
    foto_url = _guardar_foto_candidato(request.files.get("foto"), c.id)
    if foto_url:
        _eliminar_foto_si_existe(c.foto_url)
        c.foto_url = foto_url

    avisos = []
    if cambia_datos_electorales:
        avisos.append("no se cambió el nombre ni el número de lista")
    else:
        c.nombre = nombre
        c.numero_lista = numero_lista

    # Categorías: agregar categorías nuevas siempre está permitido. Solo se
    # protege (no se quita) una categoría en la que ESE candidato ya tiene votos.
    categorias_actuales_ids = {link.category_id for link in c.category_links}
    categorias_con_voto = _categorias_con_voto_por_candidato(c.id)
    a_quitar = (categorias_actuales_ids - categoria_ids) - categorias_con_voto
    bloqueadas = (categorias_actuales_ids - categoria_ids) & categorias_con_voto
    a_agregar = categoria_ids - categorias_actuales_ids

    for link in list(c.category_links):
        if link.category_id in a_quitar:
            db.session.delete(link)
    for cid in a_agregar:
        db.session.add(CandidateCategory(candidate_id=c.id, category_id=cid))

    if bloqueadas:
        avisos.append("no se quitaron las categorías en las que ya tiene votos")

    db.session.commit()
    if avisos:
        flash("Candidato actualizado: " + "; y ".join(avisos) + ", para proteger la integridad electoral.", "warning")
    else:
        flash("Candidato actualizado correctamente.", "success")
    return redirect(url_for("admin.candidatos"))

@admin_bp.route("/candidatos/<int:candidate_id>/eliminar", methods=["POST"])
@login_required
@admin_required
@permission_required("candidatos")
def eliminar_candidato(candidate_id):
    c = Candidate.query.get_or_404(candidate_id)
    if _votos_candidato(c.id):
        flash("No se puede eliminar un candidato que ya tiene votos. Puedes desactivarlo.", "danger")
        return redirect(url_for("admin.candidatos"))
    _eliminar_foto_si_existe(c.foto_url)
    db.session.delete(c)
    db.session.commit()
    flash("Candidato eliminado.", "info")
    return redirect(url_for("admin.candidatos"))


@admin_bp.route("/candidatos/<int:candidate_id>/toggle", methods=["POST"])
@login_required
@admin_required
@permission_required("candidatos")
def toggle_candidato(candidate_id):
    c = Candidate.query.get_or_404(candidate_id)
    # Activar/desactivar no altera los votos históricos; solo controla si aparece para votar.
    c.estado = "inactivo" if c.estado == "activo" else "activo"
    AuditLog.log("cambiar_estado_candidato", user_id=current_user.id, entidad="candidates", entidad_id=c.id, detalle=c.estado, ip=request.remote_addr)
    db.session.commit()
    return redirect(url_for("admin.candidatos"))


# ---------------------------------------------------------------- VOTANTES (padrón)
@admin_bp.route("/votantes")
@login_required
@admin_required
@permission_required("votantes")
def votantes():
    lista = Voter.query.order_by(Voter.nombre_completo).all()
    return render_template("admin/votantes.html", votantes=lista)


@admin_bp.route("/votantes/nuevo", methods=["POST"])
@login_required
@admin_required
@permission_required("votantes")
def nuevo_votante():
    nombre = normalizar_nombre(request.form.get("nombre_completo", ""))
    codigo = normalizar_carnet(request.form.get("codigo_padron", ""))

    if not nombre or len(nombre.split()) < 2:
        flash("Ingresa el nombre completo del votante (nombre y apellido).", "danger")
        return redirect(url_for("admin.votantes"))
    if not codigo:
        flash("El carnet es obligatorio.", "danger")
        return redirect(url_for("admin.votantes"))
    if Voter.buscar_por_nombre(nombre):
        flash("Ya existe un votante registrado con ese nombre en el padrón.", "danger")
        return redirect(url_for("admin.votantes"))
    if Voter.query.filter_by(codigo_padron=codigo).first():
        flash("Ese carnet ya está registrado en el padrón.", "danger")
        return redirect(url_for("admin.votantes"))

    try:
        v = Voter(nombre_completo=nombre, codigo_padron=codigo, estado="activo")
        db.session.add(v)
        db.session.flush()
        AuditLog.log("registrar_votante", user_id=current_user.id, entidad="voters",
                     entidad_id=v.id, detalle=f"Nombre: {nombre}; Carnet: {codigo}", ip=request.remote_addr)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("No se pudo registrar el votante. Verifica que nombre y carnet sean únicos.", "danger")
        return redirect(url_for("admin.votantes"))

    flash("Votante agregado al padrón.", "success")
    return redirect(url_for("admin.votantes"))


@admin_bp.route("/votantes/<int:voter_id>/editar", methods=["POST"])
@login_required
@admin_required
@permission_required("votantes")
def editar_votante(voter_id):
    v = Voter.query.get_or_404(voter_id)
    nombre = normalizar_nombre(request.form.get("nombre_completo", ""))
    codigo = normalizar_carnet(request.form.get("codigo_padron", ""))

    if not nombre or len(nombre.split()) < 2:
        flash("Ingresa el nombre completo.", "danger")
        return redirect(url_for("admin.votantes"))
    if not codigo:
        flash("El carnet es obligatorio.", "danger")
        return redirect(url_for("admin.votantes"))

    otro_nombre = Voter.query.filter(
        Voter.id != v.id, db.func.lower(Voter.nombre_completo) == nombre.lower()
    ).first()
    if otro_nombre:
        flash("Ya existe otro votante con ese nombre.", "danger")
        return redirect(url_for("admin.votantes"))

    otro_carnet = Voter.query.filter(Voter.id != v.id, Voter.codigo_padron == codigo).first()
    if otro_carnet:
        flash("Ese carnet ya pertenece a otro votante.", "danger")
        return redirect(url_for("admin.votantes"))

    # Una vez emitido un voto, la identidad queda congelada para preservar la auditoría.
    tiene_votos = VoteReceipt.query.filter_by(voter_id=v.id).first() is not None
    if tiene_votos and (nombre != v.nombre_completo or codigo != v.codigo_padron):
        flash("No se puede cambiar nombre o carnet de un votante que ya emitió un voto. Puedes desactivarlo.", "warning")
        return redirect(url_for("admin.votantes"))

    anterior = f"Nombre: {v.nombre_completo}; Carnet: {v.codigo_padron}"
    try:
        v.nombre_completo = nombre
        v.codigo_padron = codigo
        AuditLog.log("editar_votante", user_id=current_user.id, entidad="voters", entidad_id=v.id,
                     detalle=f"Antes: {anterior}; Después: Nombre: {nombre}; Carnet: {codigo}",
                     ip=request.remote_addr)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("No se pudo modificar el votante. Verifica que nombre y carnet sean únicos.", "danger")
        return redirect(url_for("admin.votantes"))

    flash("Votante actualizado correctamente.", "success")
    return redirect(url_for("admin.votantes"))


@admin_bp.route("/votantes/<int:voter_id>/toggle", methods=["POST"])
@login_required
@admin_required
@permission_required("votantes")
def toggle_votante(voter_id):
    v = Voter.query.get_or_404(voter_id)
    v.estado = "inactivo" if v.estado == "activo" else "activo"
    db.session.commit()
    return redirect(url_for("admin.votantes"))


@admin_bp.route("/votantes/importar", methods=["POST"])
@login_required
@admin_required
@permission_required("votantes")
def importar_votantes():
    """Importación masiva CSV: nombre_completo,codigo_padron. Ambos son obligatorios y únicos."""
    import csv
    import io

    archivo = request.files.get("archivo_csv")
    if not archivo or not archivo.filename:
        flash("Selecciona un archivo CSV.", "danger")
        return redirect(url_for("admin.votantes"))

    try:
        contenido = archivo.stream.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        flash("El CSV debe estar guardado en UTF-8.", "danger")
        return redirect(url_for("admin.votantes"))

    lector = csv.DictReader(io.StringIO(contenido))
    creados = omitidos = 0
    try:
        for fila in lector:
            nombre = normalizar_nombre(fila.get("nombre_completo") or fila.get("nombre") or "")
            codigo = normalizar_carnet(fila.get("codigo_padron") or fila.get("carnet") or "")
            if not nombre or len(nombre.split()) < 2 or not codigo:
                omitidos += 1
                continue
            if Voter.buscar_por_nombre(nombre) or Voter.query.filter_by(codigo_padron=codigo).first():
                omitidos += 1
                continue
            db.session.add(Voter(nombre_completo=nombre, codigo_padron=codigo, estado="activo"))
            creados += 1
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("La importación no pudo completarse. Revisa que nombre y carnet sean únicos.", "danger")
        return redirect(url_for("admin.votantes"))

    flash(f"{creados} votantes importados. {omitidos} filas omitidas por datos faltantes o duplicados.", "success")
    return redirect(url_for("admin.votantes"))


@admin_bp.route("/votantes/<int:voter_id>/eliminar", methods=["POST"])
@login_required
@admin_required
@permission_required("votantes")
def eliminar_votante(voter_id):
    v = Voter.query.get_or_404(voter_id)
    if VoteReceipt.query.filter_by(voter_id=v.id).first():
        flash("No se puede eliminar un votante que ya tiene comprobantes de votación. Desactívalo en su lugar.", "danger")
        return redirect(url_for("admin.votantes"))
    db.session.delete(v)
    db.session.commit()
    flash("Votante eliminado del padrón.", "info")
    return redirect(url_for("admin.votantes"))


# --------------------------------------------------------------- RESULTADOS
@admin_bp.route("/resultados")
@login_required
@admin_required
@permission_required("resultados")
def resultados():
    election = Election.query.order_by(Election.fecha_inicio.desc()).first()
    categoria_id = request.args.get("categoria_id", type=int)

    categorias_q = Category.query.filter_by(election_id=election.id) if election else Category.query.filter(False)
    if categoria_id:
        categorias_q = categorias_q.filter_by(id=categoria_id)
    categorias = categorias_q.order_by(Category.orden).all()

    tabla_resultados = []
    for cat in categorias:
        conteo = (
            db.session.query(Candidate.id, Candidate.nombre, db.func.count(Vote.id))
            .join(CandidateCategory, CandidateCategory.candidate_id == Candidate.id)
            .outerjoin(Vote, (Vote.candidate_id == Candidate.id) & (Vote.category_id == cat.id) & (Vote.election_id == cat.election_id))
            .filter(CandidateCategory.category_id == cat.id)
            .group_by(Candidate.id, Candidate.nombre)
            .order_by(db.func.count(Vote.id).desc(), Candidate.nombre.asc())
            .all()
        )
        total_votos = sum(v for _, v in conteo)
        filas = [
            {
                "candidate_id": candidate_id,
                "nombre": nombre,
                "votos": votos,
                "pct": round((votos / total_votos) * 100) if total_votos else 0,
            }
            for candidate_id, nombre, votos in conteo
        ]
        tabla_resultados.append({"categoria": cat, "filas": filas, "total_votos": total_votos})

    total_general = Vote.query.filter_by(election_id=election.id).count() if election else 0
    return render_template(
        "admin/resultados.html",
        election=election, tabla_resultados=tabla_resultados,
        total_general=total_general, categoria_id=categoria_id,
    )



@admin_bp.route("/resultados/resetear-candidato/<int:category_id>/<int:candidate_id>", methods=["POST"])
@login_required
@admin_required
@superadmin_required
def resetear_votos_candidato(category_id, candidate_id):
    """Pone en cero únicamente los votos de un candidato dentro de una categoría.
    No modifica votos de otros candidatos/categorías ni borra comprobantes de votación.
    """
    election = Election.query.order_by(Election.fecha_inicio.desc()).first()
    if not election:
        flash("No existe una elección para modificar.", "danger")
        return redirect(url_for("admin.resultados"))

    category = Category.query.filter_by(
        id=category_id, election_id=election.id
    ).first_or_404()

    candidate = Candidate.query.get_or_404(candidate_id)

    # Verifica que el participante realmente esté inscrito en esa categoría.
    link = CandidateCategory.query.filter_by(
        candidate_id=candidate.id, category_id=category.id
    ).first()
    if not link:
        flash("El participante no pertenece a esta categoría.", "danger")
        return redirect(url_for("admin.resultados"))

    try:
        total = Vote.query.filter_by(
            election_id=election.id,
            category_id=category.id,
            candidate_id=candidate.id,
        ).count()

        if total == 0:
            flash(
                f"{candidate.nombre} no tiene votos para resetear en {category.nombre}.",
                "info",
            )
            return redirect(url_for("admin.resultados"))

        Vote.query.filter_by(
            election_id=election.id,
            category_id=category.id,
            candidate_id=candidate.id,
        ).delete(synchronize_session=False)

        AuditLog.log(
            "resetear_votos_candidato",
            user_id=current_user.id,
            entidad="candidates",
            entidad_id=candidate.id,
            detalle=(
                f"Candidato: {candidate.nombre}; categoría: {category.nombre}; "
                f"votos eliminados: {total}"
            ),
            ip=request.remote_addr,
        )
        db.session.commit()

        flash(
            f"Se resetearon {total} voto(s) de {candidate.nombre} "
            f"en la categoría {category.nombre}. Los demás votos no fueron modificados.",
            "success",
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Error reseteando votos del candidato %s en categoría %s",
            candidate.id, category.id
        )
        flash("No se pudieron resetear los votos del participante.", "danger")

    return redirect(url_for("admin.resultados"))


@admin_bp.route("/resultados/exportar/<formato>")
@login_required
@admin_required
@permission_required("resultados")
def exportar_resultados(formato):
    """Exporta resultados a CSV. Para PDF, reutilizar la lógica de resultados()
    y generarlo con una librería como WeasyPrint o reportlab."""
    import csv
    import io
    from flask import Response

    if formato.lower() != "csv":
        flash("Formato de exportación no disponible. Usa CSV.", "warning")
        return redirect(url_for("admin.resultados"))
    election = Election.query.order_by(Election.fecha_inicio.desc()).first()
    if not election:
        flash("No existe una elección para exportar.", "warning")
        return redirect(url_for("admin.resultados"))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Categoría", "Candidato", "Votos"])

    for cat in Category.query.filter_by(election_id=election.id).all():
        conteo = (
            db.session.query(Candidate.nombre, db.func.count(Vote.id))
            .join(CandidateCategory, CandidateCategory.candidate_id == Candidate.id)
            .outerjoin(Vote, (Vote.candidate_id == Candidate.id) & (Vote.category_id == cat.id) & (Vote.election_id == cat.election_id))
            .filter(CandidateCategory.category_id == cat.id)
            .group_by(Candidate.id, Candidate.nombre)
            .order_by(Candidate.nombre.asc())
            .all()
        )
        for nombre, votos in conteo:
            writer.writerow([cat.nombre, nombre, votos])

    return Response(
        output.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=resultados.csv"},
    )


# ---------------------------------------------------------------------- API
@admin_bp.route("/api/stats")
@login_required
@admin_required
def api_stats():
    """Endpoint JSON opcional para alimentar el frontend (SPA/React) sin recargar página."""
    election = Election.query.order_by(Election.fecha_inicio.desc()).first()
    total_votantes = Voter.query.count()
    if election:
        iniciaron = db.session.query(VoteReceipt.voter_id).filter(VoteReceipt.election_id == election.id).distinct().count()
        total_recibos = db.session.query(VoteReceipt.voter_id).filter(VoteReceipt.election_id == election.id).distinct().count()
        completaron = total_recibos
    else:
        iniciaron = completaron = 0
    return jsonify({
        "election": election.nombre if election else None,
        "estado": election.estado if election else None,
        "total_votantes": total_votantes,
        "iniciaron": iniciaron,
        "completaron": completaron,
        "participacion_pct": round((iniciaron / total_votantes) * 100) if total_votantes else 0,
    })



# --------------------------------------------------------------- ADMINISTRADORES
@admin_bp.route("/usuarios")
@login_required
@admin_required
@superadmin_required
def usuarios():
    lista = User.query.order_by(User.nombre).all()
    return render_template("admin/usuarios.html", usuarios=lista)


@admin_bp.route("/usuarios/nuevo", methods=["POST"])
@login_required
@admin_required
@superadmin_required
def nuevo_usuario():
    nombre = request.form.get("nombre", "").strip()
    correo = request.form.get("correo", "").strip().lower()
    usuario = request.form.get("usuario", "").strip()
    password = request.form.get("password", "")
    if not nombre or not correo or not usuario or len(password) < 8:
        flash("Completa todos los datos. La contraseña debe tener al menos 8 caracteres.", "danger")
        return redirect(url_for("admin.usuarios"))
    if User.query.filter((User.correo == correo) | (User.usuario == usuario)).first():
        flash("El correo o nombre de usuario ya está registrado.", "danger")
        return redirect(url_for("admin.usuarios"))
    u = User(nombre=nombre, correo=correo, usuario=usuario, rol="admin", estado="activo")
    u.set_password(password)
    db.session.add(u); db.session.flush()
    a = Admin(user_id=u.id, nivel=request.form.get("nivel") if request.form.get("nivel") in ("admin","superadmin") else "admin")
    for permiso in ("elecciones","categorias","candidatos","votantes","resultados","usuarios"):
        setattr(a, f"puede_{permiso}", bool(request.form.get(f"puede_{permiso}")))
    db.session.add(a)
    AuditLog.log("crear_administrador", user_id=current_user.id, entidad="users", entidad_id=u.id, detalle=u.usuario, ip=request.remote_addr)
    db.session.commit()
    flash("Administrador creado correctamente.", "success")
    return redirect(url_for("admin.usuarios"))


@admin_bp.route("/usuarios/<int:user_id>/editar", methods=["POST"])
@login_required
@admin_required
@superadmin_required
def editar_usuario(user_id):
    u = User.query.get_or_404(user_id)
    a = u.admin_profile
    if not a:
        flash("La cuenta no tiene perfil administrativo.", "danger")
        return redirect(url_for("admin.usuarios"))
    u.nombre = request.form.get("nombre", u.nombre).strip()
    u.correo = request.form.get("correo", u.correo).strip().lower()
    if u.id != current_user.id:
        u.estado = "activo" if request.form.get("estado") == "activo" else "inactivo"
    nivel = request.form.get("nivel")
    if u.id != current_user.id and nivel in ("admin", "superadmin"):
        a.nivel = nivel
    for permiso in ("elecciones","categorias","candidatos","votantes","resultados","usuarios"):
        setattr(a, f"puede_{permiso}", bool(request.form.get(f"puede_{permiso}")))
    password = request.form.get("password", "")
    if password:
        if len(password) < 8:
            flash("La nueva contraseña debe tener al menos 8 caracteres.", "danger")
            return redirect(url_for("admin.usuarios"))
        u.set_password(password)
    AuditLog.log("editar_administrador", user_id=current_user.id, entidad="users", entidad_id=u.id, detalle=u.usuario, ip=request.remote_addr)
    db.session.commit()
    flash("Administrador actualizado.", "success")
    return redirect(url_for("admin.usuarios"))


@admin_bp.route("/usuarios/<int:user_id>/toggle", methods=["POST"])
@login_required
@admin_required
@superadmin_required
def toggle_usuario(user_id):
    u = User.query.get_or_404(user_id)
    if u.id == current_user.id:
        flash("No puedes desactivar tu propia cuenta mientras estás conectado.", "warning")
        return redirect(url_for("admin.usuarios"))
    u.estado = "inactivo" if u.estado == "activo" else "activo"
    AuditLog.log("cambiar_estado_administrador", user_id=current_user.id, entidad="users", entidad_id=u.id, detalle=u.estado, ip=request.remote_addr)
    db.session.commit()
    flash(f"Administrador {u.estado}.", "success")
    return redirect(url_for("admin.usuarios"))
