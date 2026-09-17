-- =====================================================================
-- DATOS DE DEMOSTRACIÓN
-- Importar DESPUÉS de schema.sql
--
-- Acceso de administrador:
--   usuario: admin / contraseña: admin123
--
-- Acceso de votante (SIN usuario/contraseña):
--   En la pantalla /votar, escribir el nombre completo tal cual aparece
--   en la tabla `voters`, por ejemplo: "Juan Pérez Alcón"
-- =====================================================================

SET FOREIGN_KEY_CHECKS = 0;

-- 1) USERS (solo administradores) --------------------------------------
INSERT INTO users (id, nombre, correo, usuario, password_hash, rol, estado) VALUES
(1, 'Administrador del Sistema', 'admin@jeronet.bo', 'admin',
 'scrypt:32768:8:1$KmVvoEmFteUGwVHr$6c290f5789ba6553532af84948281c0b580d2fbf2a15aebbf9dd33bae4d71c090e9708ebc9e0b3461465eacdbc417bf84959b16c166b6b1ed6a7429aa3e4e308',
 'admin', 'activo');

-- 2) ADMINS ---------------------------------------------------------------
INSERT INTO admins (user_id, nivel) VALUES (1, 'superadmin');

-- 3) VOTERS (padrón, solo nombre completo + código opcional) --------------
INSERT INTO voters (id, nombre_completo, codigo_padron, estado, iniciado, terminado) VALUES
(1, 'Juan Pérez Alcón',      'PAD-0001', 'activo', 1, 0),
(2, 'María Fernanda Soliz',  'PAD-0002', 'activo', 1, 1),
(3, 'Carlos Andrade Vega',   'PAD-0003', 'activo', 0, 0),
(4, 'Rocío Ibáñez Castro',   'PAD-0004', 'activo', 1, 0),
(5, 'Tomás Vargas Solano',   'PAD-0005', 'inactivo', 0, 0);

-- 4) ELECTIONS ------------------------------------------------------------
-- Fechas dinámicas (NOW() -1 día / +5 días) para que la elección quede
-- ACTIVA de inmediato al importar este archivo. Para producción, reemplaza
-- fecha_inicio/fecha_fin por fechas fijas reales de tu proceso electoral.
INSERT INTO elections (id, nombre, descripcion, institucion, estado, fecha_inicio, fecha_fin, resultados_publicos, secreta, created_by) VALUES
(1, 'Elecciones Centro de Estudiantes 2026',
 'Renovación de autoridades del Centro de Estudiantes, gestión 2026-2027.',
 'Universidad Mayor de San Andrés', 'activa',
 DATE_SUB(NOW(), INTERVAL 1 DAY), DATE_ADD(NOW(), INTERVAL 5 DAY), 0, 1, 1);

-- 5) CATEGORIES -----------------------------------------------------------
INSERT INTO categories (id, election_id, nombre, descripcion, orden, estado, max_selecciones, obligatoria) VALUES
(1, 1, 'Presidente', 'Máxima autoridad del Centro de Estudiantes.', 1, 'activa', 1, 1),
(2, 1, 'Vicepresidente', 'Segunda autoridad, asume en ausencia del titular.', 2, 'activa', 1, 1),
(3, 1, 'Secretario General', 'Encargado de actas, comunicación y archivo.', 3, 'activa', 1, 1),
(4, 1, 'Tesorero', 'Administración de fondos y rendición de cuentas.', 4, 'activa', 1, 1),
(5, 1, 'Representante Estudiantil', 'Voz del estudiantado ante el consejo facultativo.', 5, 'activa', 1, 1),
(6, 1, 'Vocal', 'Apoyo en organización de actividades y eventos.', 6, 'activa', 2, 0);

-- 6) CANDIDATES -------------------------------------------------------------
-- foto_url queda NULL: sube la fotografía real desde el panel de administración
-- (Candidatos -> editar candidato -> subir fotografía). Mientras no haya foto,
-- el frontend muestra las iniciales del candidato como avatar.
INSERT INTO candidates (id, nombre, numero_lista, agrupacion, propuesta, foto_url, estado) VALUES
(1,  'Marcela Fernández Rojas',   '01', 'Frente Renovación',       'Impulsar becas de investigación y ampliar horarios de biblioteca.', NULL, 'activo'),
(2,  'Luis Ángel Quispe Mamani',  '02', 'Unidad Estudiantil',      'Transporte gratuito los sábados y wifi en todas las aulas.', NULL, 'activo'),
(3,  'Daniela Choque Villca',     '03', 'Movimiento Independiente','Comedor universitario con precios subvencionados.', NULL, 'activo'),
(4,  'Jorge Iván Callisaya',      '01', 'Frente Renovación',       'Coordinación directa con decanato para pasantías.', NULL, 'activo'),
(5,  'Camila Torrez Aguilar',     '02', 'Unidad Estudiantil',      'Programa de mentoría entre pares.', NULL, 'activo'),
(6,  'Rodrigo Mamani Huanca',     '01', 'Frente Renovación',       'Actas públicas de cada reunión del centro.', NULL, 'activo'),
(7,  'Valeria Sánchez Poma',      '02', 'Movimiento Independiente','Digitalizar trámites y reducir filas.', NULL, 'activo'),
(8,  'Esteban Rocha Ticona',      '01', 'Unidad Estudiantil',      'Auditoría trimestral abierta a todos los afiliados.', NULL, 'activo'),
(9,  'Andrea Paredes Cusi',       '02', 'Frente Renovación',       'Fondo de emergencia estudiantil.', NULL, 'activo'),
(10, 'Franz Aliaga Nina',         '03', 'Movimiento Independiente','Becas deportivas y culturales ampliadas.', NULL, 'activo'),
(11, 'Ana Belén Yujra',           '01', 'Frente Renovación',       'Representación directa en consejo facultativo.', NULL, 'activo'),
(12, 'Diego Armando Choquehuanca','02', 'Unidad Estudiantil',      'Encuestas mensuales de necesidades estudiantiles.', NULL, 'activo'),
(13, 'Paola Ramírez Villalba',    '01', 'Movimiento Independiente','Talleres gratuitos de oratoria y liderazgo.', NULL, 'activo'),
(14, 'Sergio Mendoza Apaza',      '02', 'Frente Renovación',       'Espacios de estudio 24 horas en época de exámenes.', NULL, 'activo'),
(15, 'Grecia Limachi Flores',     '03', 'Unidad Estudiantil',      'Convenios con editoriales para libros a bajo costo.', NULL, 'activo');

-- 7) CANDIDATE_CATEGORIES ----------------------------------------------------
INSERT INTO candidate_categories (candidate_id, category_id) VALUES
(1,1), (2,1), (3,1),
(4,2), (5,2),
(6,3), (7,3),
(8,4), (9,4), (10,4),
(11,5), (12,5),
(13,6), (14,6), (15,6);

-- 8) VOTE_RECEIPTS (comprobantes de que ya votaron, sin revelar candidato) --
-- Juan Pérez Alcón (voter_id=1) ya votó en Presidente, Vicepresidente y Rep. Estudiantil
INSERT INTO vote_receipts (voter_id, category_id, election_id, codigo_comprobante) VALUES
(1, 1, 1, 'RCPT-0001-0001'),
(1, 2, 1, 'RCPT-0001-0002'),
(1, 5, 1, 'RCPT-0001-0005'),
(2, 1, 1, 'RCPT-0002-0001'),
(2, 2, 1, 'RCPT-0002-0002'),
(2, 3, 1, 'RCPT-0002-0003'),
(2, 4, 1, 'RCPT-0002-0004'),
(2, 5, 1, 'RCPT-0002-0005'),
(2, 6, 1, 'RCPT-0002-0006'),
(4, 1, 1, 'RCPT-0004-0001'),
(4, 3, 1, 'RCPT-0004-0003');

-- 9) VOTES (anónimos: voter_id queda NULL porque la elección es secreta) ---
-- Lote reducido de ejemplo para poblar resultados; el volumen mayor se
-- genera automáticamente si usas `flask seed-db` en vez de este archivo.
INSERT INTO votes (election_id, category_id, candidate_id, voter_id) VALUES
(1,1,1,NULL), (1,1,1,NULL), (1,1,2,NULL), (1,1,3,NULL),
(1,2,4,NULL), (1,2,5,NULL),
(1,3,6,NULL), (1,3,7,NULL),
(1,4,8,NULL), (1,4,9,NULL), (1,4,10,NULL),
(1,5,11,NULL), (1,5,12,NULL),
(1,6,13,NULL), (1,6,14,NULL), (1,6,15,NULL);

-- 10) ELECTION_SETTINGS ------------------------------------------------------
INSERT INTO election_settings (election_id, clave, valor) VALUES
(1, 'permite_reintentos', '0'),
(1, 'notificar_por_correo', '1'),
(1, 'zona_horaria', 'America/La_Paz');

-- 11) AUDIT_LOGS --------------------------------------------------------------
INSERT INTO audit_logs (user_id, voter_id, accion, entidad, entidad_id, detalle, ip) VALUES
(1, NULL, 'login', 'users', 1, 'Inicio de sesión de administrador', '127.0.0.1'),
(1, NULL, 'crear_eleccion', 'elections', 1, 'Creación de Elecciones Centro de Estudiantes 2026', '127.0.0.1'),
(NULL, 1, 'identificacion_votante', 'voters', 1, 'Juan Pérez Alcón', '127.0.0.1');

SET FOREIGN_KEY_CHECKS = 1;
