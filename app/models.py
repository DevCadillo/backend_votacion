import re
import secrets
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


def normalizar_carnet(carnet):
    """Normaliza el carnet para evitar duplicados por espacios o mayúsculas."""
    if carnet is None:
        return ""
    return "".join(str(carnet).strip().upper().split())


def normalizar_nombre(nombre):
    """Recorta espacios extra y colapsa espacios múltiples, para poder
    comparar nombres de forma consistente sin importar cómo los tipee el votante."""
    return re.sub(r"\s+", " ", (nombre or "").strip())


class User(db.Model, UserMixin):
    """Cuenta de acceso — SOLO para administradores.
    Los votantes ya no tienen usuario/contraseña: ver la clase Voter."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    correo = db.Column(db.String(150), unique=True, nullable=False)
    usuario = db.Column(db.String(60), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.Enum("admin", name="rol_enum"), nullable=False, default="admin")
    estado = db.Column(db.Enum("activo", "inactivo", name="estado_user_enum"), nullable=False, default="activo")
    ultimo_acceso = db.Column(db.DateTime, nullable=True)
    reset_token = db.Column(db.String(120), nullable=True)
    reset_expira = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    admin_profile = db.relationship("Admin", backref="user", uselist=False, cascade="all, delete-orphan")

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    def generate_reset_token(self):
        self.reset_token = secrets.token_urlsafe(32)
        return self.reset_token

    @property
    def is_admin(self):
        return self.rol == "admin"

    @property
    def is_active(self):
        return self.estado == "activo"

    def __repr__(self):
        return f"<User {self.usuario} ({self.rol})>"


class Admin(db.Model):
    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False
    )

    nivel = db.Column(
        db.Enum("superadmin", "admin", name="nivel_admin_enum"),
        nullable=False,
        default="admin"
    )

    # Permisos del administrador
    puede_elecciones = db.Column(db.Boolean, nullable=False, default=True)
    puede_categorias = db.Column(db.Boolean, nullable=False, default=True)
    puede_candidatos = db.Column(db.Boolean, nullable=False, default=True)
    puede_votantes = db.Column(db.Boolean, nullable=False, default=True)
    puede_resultados = db.Column(db.Boolean, nullable=False, default=True)
    puede_usuarios = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Admin {self.id} - User {self.user_id}>"

class Voter(db.Model):
    """
    Padrón de votantes habilitados. NO tiene usuario ni contraseña.
    El carnet es el identificador único. Si no existe, el sistema solicita
    nombre completo y carnet para crear el registro.
    """
    __tablename__ = "voters"

    id = db.Column(db.Integer, primary_key=True)
    nombre_completo = db.Column(db.String(180), nullable=False, unique=True)
    codigo_padron = db.Column(db.String(40), nullable=False, unique=True)
    estado = db.Column(db.Enum("activo", "inactivo", name="estado_voter_enum"), nullable=False, default="activo")
    iniciado = db.Column(db.Boolean, default=False)
    terminado = db.Column(db.Boolean, default=False)
    terminado_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    receipts = db.relationship("VoteReceipt", backref="voter", cascade="all, delete-orphan")

    @staticmethod
    def buscar_por_nombre(nombre):
        objetivo = normalizar_nombre(nombre)
        if not objetivo:
            return None
        return Voter.query.filter(db.func.lower(Voter.nombre_completo) == objetivo.lower()).first()

    def progreso_pct(self, election):
        total = Category.query.filter_by(election_id=election.id, estado="activa").count()
        if total == 0:
            return 0
        completadas = VoteReceipt.query.filter_by(voter_id=self.id, election_id=election.id).count()
        return round((completadas / total) * 100)


class Election(db.Model):
    __tablename__ = "elections"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    institucion = db.Column(db.String(200), nullable=True)
    estado = db.Column(db.Enum("proxima", "activa", "finalizada", name="estado_eleccion_enum"), default="proxima")
    fecha_inicio = db.Column(db.DateTime, nullable=False)
    fecha_fin = db.Column(db.DateTime, nullable=False)
    resultados_publicos = db.Column(db.Boolean, default=False)
    secreta = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    categories = db.relationship("Category", backref="election", cascade="all, delete-orphan", order_by="Category.orden")
    settings = db.relationship("ElectionSetting", backref="election", cascade="all, delete-orphan")

    def esta_en_fecha(self):
        now = datetime.utcnow()
        return self.fecha_inicio <= now <= self.fecha_fin

    def puede_votar(self):
        return self.estado == "activa" and self.esta_en_fecha()


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    election_id = db.Column(db.Integer, db.ForeignKey("elections.id", ondelete="CASCADE"), nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    orden = db.Column(db.Integer, default=1)
    estado = db.Column(db.Enum("activa", "inactiva", name="estado_categoria_enum"), default="activa")
    max_selecciones = db.Column(db.Integer, default=1)
    obligatoria = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    candidate_links = db.relationship("CandidateCategory", backref="category", cascade="all, delete-orphan")

    @property
    def candidatos(self):
        return [link.candidate for link in self.candidate_links]


class Candidate(db.Model):
    __tablename__ = "candidates"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    numero_lista = db.Column(db.String(20), nullable=True)
    agrupacion = db.Column(db.String(150), nullable=True)
    descripcion = db.Column(db.Text, nullable=True)
    propuesta = db.Column(db.Text, nullable=True)
    foto_url = db.Column(db.String(255), nullable=True)
    estado = db.Column(db.Enum("activo", "inactivo", name="estado_candidato_enum"), default="activo")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category_links = db.relationship("CandidateCategory", backref="candidate", cascade="all, delete-orphan")

    @property
    def iniciales(self):
        partes = self.nombre.split()
        return "".join(p[0] for p in partes[:2]).upper() if partes else "??"


class CandidateCategory(db.Model):
    """Tabla puente: un candidato puede pertenecer a varias categorías."""
    __tablename__ = "candidate_categories"

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("candidate_id", "category_id", name="uq_candidate_category"),)


class VoteReceipt(db.Model):
    """
    Comprobante de que un votante ya emitió su voto en una categoría.
    NO contiene el candidato elegido: eso vive en Vote, desligado del votante
    cuando la elección es secreta. Así se separa identidad de selección.
    """
    __tablename__ = "vote_receipts"

    id = db.Column(db.Integer, primary_key=True)
    voter_id = db.Column(db.Integer, db.ForeignKey("voters.id", ondelete="CASCADE"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    election_id = db.Column(db.Integer, db.ForeignKey("elections.id", ondelete="CASCADE"), nullable=False)
    codigo_comprobante = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("voter_id", "election_id", "category_id", name="uq_receipt_voter_election_category"),)


class Vote(db.Model):
    """Voto emitido. voter_id queda NULL si la elección es secreta (anónimo)."""
    __tablename__ = "votes"

    id = db.Column(db.Integer, primary_key=True)
    election_id = db.Column(db.Integer, db.ForeignKey("elections.id", ondelete="CASCADE"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    voter_id = db.Column(db.Integer, db.ForeignKey("voters.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ElectionSetting(db.Model):
    __tablename__ = "election_settings"

    id = db.Column(db.Integer, primary_key=True)
    election_id = db.Column(db.Integer, db.ForeignKey("elections.id", ondelete="CASCADE"), nullable=False)
    clave = db.Column(db.String(80), nullable=False)
    valor = db.Column(db.String(255), nullable=True)

    __table_args__ = (db.UniqueConstraint("election_id", "clave", name="uq_setting_election_clave"),)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    voter_id = db.Column(db.Integer, db.ForeignKey("voters.id", ondelete="SET NULL"), nullable=True)
    accion = db.Column(db.String(100), nullable=False)
    entidad = db.Column(db.String(60), nullable=True)
    entidad_id = db.Column(db.Integer, nullable=True)
    detalle = db.Column(db.Text, nullable=True)
    ip = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @staticmethod
    def log(accion, user_id=None, voter_id=None, entidad=None, entidad_id=None, detalle=None, ip=None):
        entry = AuditLog(user_id=user_id, voter_id=voter_id, accion=accion, entidad=entidad,
                          entidad_id=entidad_id, detalle=detalle, ip=ip)
        db.session.add(entry)
        return entry
