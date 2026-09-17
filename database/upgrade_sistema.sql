-- ================================================================
-- ACTUALIZACIÓN DEL SISTEMA DE VOTACIÓN
-- Hacer RESPALDO de la base antes de ejecutar.
-- ================================================================

-- A. Detectar datos que impiden carnet obligatorio/único:
SELECT id, nombre_completo, codigo_padron FROM voters
WHERE codigo_padron IS NULL OR TRIM(codigo_padron) = '';

SELECT codigo_padron, COUNT(*) cantidad FROM voters
WHERE codigo_padron IS NOT NULL AND TRIM(codigo_padron) <> ''
GROUP BY codigo_padron HAVING COUNT(*) > 1;

SELECT nombre_completo, COUNT(*) cantidad FROM voters
GROUP BY nombre_completo HAVING COUNT(*) > 1;

-- B. Cuando las consultas anteriores no devuelvan duplicados/vacíos:
ALTER TABLE voters MODIFY codigo_padron VARCHAR(40) NOT NULL;

-- Si uq_voters_carnet no existe:
-- ALTER TABLE voters ADD UNIQUE KEY uq_voters_carnet (codigo_padron);

-- Si uq_voters_nombre no existe:
-- ALTER TABLE voters ADD UNIQUE KEY uq_voters_nombre (nombre_completo);

-- C. Para permitir al mismo ciudadano votar en una futura elección,
-- el comprobante debe ser único por votante + elección + categoría.
-- Revisar primero el nombre del índice actual:
-- SHOW INDEX FROM vote_receipts;
-- Si existe uq_receipt_voter_category:
-- ALTER TABLE vote_receipts DROP INDEX uq_receipt_voter_category;
-- ALTER TABLE vote_receipts ADD UNIQUE KEY uq_receipt_voter_election_category (voter_id, election_id, category_id);
