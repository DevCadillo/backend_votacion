-- EJECUTAR UNA SOLA VEZ EN SUPABASE > SQL EDITOR
ALTER TABLE admins ADD COLUMN IF NOT EXISTS puede_elecciones BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE admins ADD COLUMN IF NOT EXISTS puede_categorias BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE admins ADD COLUMN IF NOT EXISTS puede_candidatos BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE admins ADD COLUMN IF NOT EXISTS puede_votantes BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE admins ADD COLUMN IF NOT EXISTS puede_resultados BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE admins ADD COLUMN IF NOT EXISTS puede_usuarios BOOLEAN NOT NULL DEFAULT FALSE;

-- Los superadministradores existentes conservan acceso total.
UPDATE admins SET puede_elecciones=TRUE, puede_categorias=TRUE, puede_candidatos=TRUE,
  puede_votantes=TRUE, puede_resultados=TRUE, puede_usuarios=TRUE
WHERE nivel='superadmin';
