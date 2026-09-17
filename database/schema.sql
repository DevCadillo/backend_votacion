-- =====================================================================
-- SISTEMA DE ELECCIONES Y VOTACIONES POR CATEGORÍAS
-- Esquema de base de datos para MySQL / phpMyAdmin
-- Motor: InnoDB | Charset: utf8mb4
--
-- Cómo importar en phpMyAdmin:
--   1. Crea una base de datos vacía, ej: elecciones_db  (utf8mb4_unicode_ci)
--   2. Entra a esa base -> pestaña "Importar" -> selecciona este archivo -> Continuar
--   3. Luego importa seed.sql si quieres los datos de demostración
-- =====================================================================

SET FOREIGN_KEY_CHECKS = 0;
SET NAMES utf8mb4;

-- ---------------------------------------------------------------------
-- 1. users  — cuenta de acceso SOLO para administradores.
--    Los votantes ya NO tienen usuario/contraseña: ver la tabla `voters`.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    nombre          VARCHAR(150)        NOT NULL,
    correo          VARCHAR(150)        NOT NULL,
    usuario         VARCHAR(60)         NOT NULL,
    password_hash   VARCHAR(255)        NOT NULL,
    rol             ENUM('admin')       NOT NULL DEFAULT 'admin',
    estado          ENUM('activo','inactivo') NOT NULL DEFAULT 'activo',
    ultimo_acceso   DATETIME            NULL,
    reset_token     VARCHAR(120)        NULL,
    reset_expira    DATETIME            NULL,
    created_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_users_correo (correo),
    UNIQUE KEY uq_users_usuario (usuario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 2. admins  — datos adicionales de administradores
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS admins (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id         INT UNSIGNED NOT NULL,
    nivel           ENUM('superadmin','admin') NOT NULL DEFAULT 'admin',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_admins_user (user_id),
    CONSTRAINT fk_admins_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 3. voters  — PADRÓN de votantes habilitados. SIN usuario ni contraseña:
--    el votante se identifica escribiendo su nombre completo en /votar,
--    que se compara contra nombre_completo (la collation utf8mb4_unicode_ci
--    ya hace esa comparación insensible a mayúsculas/minúsculas).
--    El administrador es quien registra/importa estos nombres.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS voters (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    nombre_completo VARCHAR(180) NOT NULL,
    codigo_padron   VARCHAR(40)  NOT NULL,
    estado          ENUM('activo','inactivo') NOT NULL DEFAULT 'activo',
    iniciado        TINYINT(1)   NOT NULL DEFAULT 0,
    terminado       TINYINT(1)   NOT NULL DEFAULT 0,
    terminado_at    DATETIME     NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_voters_nombre (nombre_completo),
    UNIQUE KEY uq_voters_carnet (codigo_padron)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 4. elections  — elecciones/procesos de votación
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS elections (
    id                  INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    nombre              VARCHAR(200) NOT NULL,
    descripcion         TEXT         NULL,
    institucion         VARCHAR(200) NULL,
    estado              ENUM('proxima','activa','finalizada') NOT NULL DEFAULT 'proxima',
    fecha_inicio        DATETIME     NOT NULL,
    fecha_fin           DATETIME     NOT NULL,
    resultados_publicos TINYINT(1)   NOT NULL DEFAULT 0,
    secreta             TINYINT(1)   NOT NULL DEFAULT 1,
    created_by          INT UNSIGNED NULL,
    created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_elections_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 5. categories  — categorías dentro de una elección (Presidente, etc.)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    election_id     INT UNSIGNED NOT NULL,
    nombre          VARCHAR(150) NOT NULL,
    descripcion     TEXT         NULL,
    orden           INT UNSIGNED NOT NULL DEFAULT 1,
    estado          ENUM('activa','inactiva') NOT NULL DEFAULT 'activa',
    max_selecciones TINYINT UNSIGNED NOT NULL DEFAULT 1,
    obligatoria     TINYINT(1)   NOT NULL DEFAULT 1,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_categories_election (election_id),
    CONSTRAINT fk_categories_election FOREIGN KEY (election_id) REFERENCES elections(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 6. candidates  — candidatos (pueden repetirse entre categorías vía junction)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS candidates (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    nombre          VARCHAR(200) NOT NULL,
    numero_lista    VARCHAR(20)  NULL,
    agrupacion      VARCHAR(150) NULL,
    descripcion     TEXT         NULL,
    propuesta       TEXT         NULL,
    foto_url        VARCHAR(255) NULL,
    estado          ENUM('activo','inactivo') NOT NULL DEFAULT 'activo',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 7. candidate_categories  — relación N:M candidato <-> categoría
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS candidate_categories (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    candidate_id    INT UNSIGNED NOT NULL,
    category_id     INT UNSIGNED NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_candidate_category (candidate_id, category_id),
    CONSTRAINT fk_cc_candidate FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE CASCADE,
    CONSTRAINT fk_cc_category  FOREIGN KEY (category_id)  REFERENCES categories(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 8. vote_receipts — comprobante de "ya votó en esta categoría"
--    Separa la IDENTIDAD del votante de la SELECCIÓN emitida (votes).
--    Es lo que permite bloquear doble voto sin romper el secreto del voto.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vote_receipts (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    voter_id        INT UNSIGNED NOT NULL,
    category_id     INT UNSIGNED NOT NULL,
    election_id     INT UNSIGNED NOT NULL,
    codigo_comprobante VARCHAR(64) NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_receipt_voter_election_category (voter_id, election_id, category_id),
    UNIQUE KEY uq_receipt_codigo (codigo_comprobante),
    CONSTRAINT fk_receipt_voter    FOREIGN KEY (voter_id)    REFERENCES voters(id)     ON DELETE CASCADE,
    CONSTRAINT fk_receipt_category FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE,
    CONSTRAINT fk_receipt_election FOREIGN KEY (election_id) REFERENCES elections(id)  ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 9. votes  — voto emitido (anónimo si la elección es secreta)
--    voter_id se guarda SOLO cuando la elección NO es secreta (nominal);
--    si es secreta, voter_id queda NULL y la trazabilidad de "quién votó"
--    vive únicamente en vote_receipts (sin ligar a la opción elegida).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS votes (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    election_id     INT UNSIGNED NOT NULL,
    category_id     INT UNSIGNED NOT NULL,
    candidate_id    INT UNSIGNED NOT NULL,
    voter_id        INT UNSIGNED NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_votes_category (category_id),
    KEY idx_votes_candidate (candidate_id),
    KEY idx_votes_election (election_id),
    CONSTRAINT fk_votes_election  FOREIGN KEY (election_id)  REFERENCES elections(id)  ON DELETE CASCADE,
    CONSTRAINT fk_votes_category  FOREIGN KEY (category_id)  REFERENCES categories(id) ON DELETE CASCADE,
    CONSTRAINT fk_votes_candidate FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE CASCADE,
    CONSTRAINT fk_votes_voter     FOREIGN KEY (voter_id)     REFERENCES voters(id)     ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 10. election_settings  — configuración clave/valor extensible por elección
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS election_settings (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    election_id     INT UNSIGNED NOT NULL,
    clave           VARCHAR(80)  NOT NULL,
    valor           VARCHAR(255) NULL,
    UNIQUE KEY uq_setting_election_clave (election_id, clave),
    CONSTRAINT fk_settings_election FOREIGN KEY (election_id) REFERENCES elections(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 11. audit_logs  — bitácora de auditoría de acciones del sistema
--     (acciones de admin -> user_id; acciones de votante -> voter_id)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id         INT UNSIGNED NULL,
    voter_id        INT UNSIGNED NULL,
    accion          VARCHAR(100) NOT NULL,
    entidad         VARCHAR(60)  NULL,
    entidad_id      INT UNSIGNED NULL,
    detalle         TEXT         NULL,
    ip              VARCHAR(45)  NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_audit_user (user_id),
    KEY idx_audit_voter (voter_id),
    KEY idx_audit_created (created_at),
    CONSTRAINT fk_audit_user  FOREIGN KEY (user_id)  REFERENCES users(id)  ON DELETE SET NULL,
    CONSTRAINT fk_audit_voter FOREIGN KEY (voter_id) REFERENCES voters(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
