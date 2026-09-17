"""
Comando: flask seed-db
Crea las tablas (si no existen) y carga datos de demostración equivalentes
a database/seed.sql, útil si prefieres poblar la BD desde Python en vez
de importar el .sql directamente en phpMyAdmin.
"""
from datetime import datetime, timedelta
import random

import click

from app.extensions import db
from app.models import (
    User, Admin, Voter, Election, Category, Candidate,
    CandidateCategory, Vote, VoteReceipt, ElectionSetting,
)

CATEGORIAS_DEMO = [
    ("Presidente", "Máxima autoridad del Centro de Estudiantes.", 1, True,
     [("Marcela Fernández Rojas", "01", "Frente Renovación", "Becas de investigación y más horas de biblioteca."),
      ("Luis Ángel Quispe Mamani", "02", "Unidad Estudiantil", "Transporte gratuito los sábados."),
      ("Daniela Choque Villca", "03", "Movimiento Independiente", "Comedor universitario subvencionado.")]),
    ("Vicepresidente", "Segunda autoridad, asume en ausencia del titular.", 2, True,
     [("Jorge Iván Callisaya", "01", "Frente Renovación", "Coordinación con decanato para pasantías."),
      ("Camila Torrez Aguilar", "02", "Unidad Estudiantil", "Programa de mentoría entre pares.")]),
    ("Secretario General", "Encargado de actas, comunicación y archivo.", 3, True,
     [("Rodrigo Mamani Huanca", "01", "Frente Renovación", "Actas públicas de cada reunión."),
      ("Valeria Sánchez Poma", "02", "Movimiento Independiente", "Digitalizar trámites.")]),
    ("Tesorero", "Administración de fondos y rendición de cuentas.", 4, True,
     [("Esteban Rocha Ticona", "01", "Unidad Estudiantil", "Auditoría trimestral abierta."),
      ("Andrea Paredes Cusi", "02", "Frente Renovación", "Fondo de emergencia estudiantil."),
      ("Franz Aliaga Nina", "03", "Movimiento Independiente", "Becas deportivas y culturales.")]),
    ("Representante Estudiantil", "Voz del estudiantado ante el consejo facultativo.", 5, True,
     [("Ana Belén Yujra", "01", "Frente Renovación", "Representación directa en consejo."),
      ("Diego Armando Choquehuanca", "02", "Unidad Estudiantil", "Encuestas mensuales de necesidades.")]),
    ("Vocal", "Apoyo en organización de actividades y eventos.", 6, False,
     [("Paola Ramírez Villalba", "01", "Movimiento Independiente", "Talleres de oratoria y liderazgo."),
      ("Sergio Mendoza Apaza", "02", "Frente Renovación", "Espacios de estudio 24h en exámenes."),
      ("Grecia Limachi Flores", "03", "Unidad Estudiantil", "Convenios con editoriales.")]),
]

# Padrón de votantes de demostración: SOLO nombre completo + código, sin cuenta.
VOTANTES_DEMO = [
    ("Juan Pérez Alcón", "PAD-0001"),
    ("María Fernanda Soliz", "PAD-0002"),
    ("Carlos Andrade Vega", "PAD-0003"),
    ("Rocío Ibáñez Castro", "PAD-0004"),
    ("Tomás Vargas Solano", "PAD-0005"),
]


def seed_database():
    db.create_all()

    if User.query.filter_by(usuario="admin").first():
        click.echo("La base de datos ya contiene datos. Nada que hacer.")
        return

    admin_user = User(nombre="Administrador del Sistema", correo="admin@jeronet.bo", usuario="admin", rol="admin")
    admin_user.set_password("admin123")
    db.session.add(admin_user)
    db.session.flush()
    db.session.add(Admin(user_id=admin_user.id, nivel="superadmin"))

    election = Election(
        nombre="Elecciones Centro de Estudiantes 2026",
        descripcion="Renovación de autoridades del Centro de Estudiantes, gestión 2026-2027.",
        institucion="Universidad Mayor de San Andrés",
        estado="activa",
        # Fechas dinámicas para que la elección quede activa apenas se siembra la BD.
        fecha_inicio=datetime.utcnow() - timedelta(days=1),
        fecha_fin=datetime.utcnow() + timedelta(days=5),
        resultados_publicos=False,
        secreta=True,
        created_by=admin_user.id,
    )
    db.session.add(election)
    db.session.flush()
    db.session.add(ElectionSetting(election_id=election.id, clave="permite_reintentos", valor="0"))

    categorias_creadas = []
    for nombre, desc, orden, obligatoria, candidatos in CATEGORIAS_DEMO:
        cat = Category(election_id=election.id, nombre=nombre, descripcion=desc,
                        orden=orden, obligatoria=obligatoria, max_selecciones=1)
        db.session.add(cat)
        db.session.flush()
        categorias_creadas.append(cat)
        for nombre_c, numero, agrupacion, propuesta in candidatos:
            cand = Candidate(nombre=nombre_c, numero_lista=numero, agrupacion=agrupacion, propuesta=propuesta)
            db.session.add(cand)
            db.session.flush()
            db.session.add(CandidateCategory(candidate_id=cand.id, category_id=cat.id))
            # votos de ejemplo para poblar resultados (anónimos)
            for _ in range(random.randint(40, 260)):
                db.session.add(Vote(election_id=election.id, category_id=cat.id, candidate_id=cand.id))

    votantes_creados = []
    for nombre, codigo in VOTANTES_DEMO:
        v = Voter(nombre_completo=nombre, codigo_padron=codigo)
        if nombre == "Tomás Vargas Solano":
            v.estado = "inactivo"  # ejemplo de votante deshabilitado por el admin
        db.session.add(v)
        db.session.flush()
        votantes_creados.append(v)

    # el primer votante (Juan) ya tiene 3 de 6 categorías votadas, para demo
    import secrets as _secrets
    for cat in categorias_creadas[:3]:
        db.session.add(VoteReceipt(
            voter_id=votantes_creados[0].id, category_id=cat.id,
            election_id=election.id, codigo_comprobante=_secrets.token_hex(16),
        ))
    votantes_creados[0].iniciado = True

    db.session.commit()
    click.echo("Base de datos poblada con datos de demostración.")
    click.echo("  Admin   -> usuario: admin / contraseña: admin123")
    click.echo("  Votante -> en /votar, escribir el nombre: 'Juan Pérez Alcón' (sin contraseña)")


def register_cli(app):
    @app.cli.command("seed-db")
    def seed_db_command():
        """Crea las tablas y carga datos de demostración."""
        seed_database()
