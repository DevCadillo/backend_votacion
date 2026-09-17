# Despliegue: Flask + Render + Supabase

Este proyecto fue adaptado de MySQL/MariaDB a PostgreSQL (Supabase).

## 1. Crear proyecto en Supabase
1. Crea un proyecto.
2. Abre SQL Editor.
3. Ejecuta `database/elecciones_supabase.sql`.
4. En Storage crea un bucket PUBLICO llamado `candidatos`.

## 2. Obtener conexión PostgreSQL
En Supabase abre **Connect** y copia **Session pooler** (puerto 5432).
Guárdala como `DATABASE_URL`. No publiques la contraseña.

## 3. Storage
En Render define:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` (solo backend; nunca exponer en frontend)
- `SUPABASE_STORAGE_BUCKET=candidatos`

Las fotos antiguas incluidas en `app/static/uploads/candidatos` siguen funcionando. Las nuevas se guardan en Supabase Storage.

## 4. Render
Sube esta carpeta a GitHub y crea un Web Service. Si Render detecta `render.yaml`, puede usarlo.

Build command:
`pip install -r requirements.txt`

Start command:
`gunicorn --bind 0.0.0.0:$PORT run:app`

Variables mínimas:
- `DATABASE_URL`
- `SECRET_KEY`
- `SESSION_COOKIE_SECURE=true`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_STORAGE_BUCKET=candidatos`

Health check opcional: `/health`.

## 5. Local
Copia `.env.example` a `.env` y cambia los valores. Luego:
`pip install -r requirements.txt`
`python run.py`

## Seguridad
No subas `.env` ni la service role key a GitHub.
