-- Comprobacion manual de T-012, hecha por el supervisor con SQL directo sobre la
-- copia de la Pi, SIN usar el codigo del resumen. Si las dos coinciden, la tabla
-- no se esta creyendo a si misma.

-- 1) Celda (plaza, hora): XETRA a las 06 UTC. La tabla dice 186/217.
SELECT COUNT(*) AS mediciones,
       SUM(CASE WHEN sessions_approx >= 1 THEN 1 ELSE 0 END) AS retrasadas
FROM data_freshness_measurement
WHERE market = 'XETRA' AND substr(measured_at, 12, 2) = '06';

-- 2) Europa contra el resto, en las cuatro pasadas programadas.
SELECT substr(measured_at, 12, 2) AS hora,
       SUM(CASE WHEN market IN ('XETRA','PAR','MCE','MIL','AMS','CPH') THEN 1 ELSE 0 END) AS n_europa,
       SUM(CASE WHEN market IN ('XETRA','PAR','MCE','MIL','AMS','CPH') AND sessions_approx >= 1 THEN 1 ELSE 0 END) AS tarde_europa,
       SUM(CASE WHEN market IN ('NASDAQ','NYSE','JPX','HKG','KSC') THEN 1 ELSE 0 END) AS n_resto,
       SUM(CASE WHEN market IN ('NASDAQ','NYSE','JPX','HKG','KSC') AND sessions_approx >= 1 THEN 1 ELSE 0 END) AS tarde_resto
FROM data_freshness_measurement
WHERE substr(measured_at, 12, 2) IN ('06','07','13','20') AND sessions_approx IS NOT NULL
GROUP BY 1 ORDER BY 1;

-- 3) Cuantas versiones de codigo cruza la ventana, y cuantas mediciones usan la
--    regla nueva de D-36/D-37 (que entra con v0.3.0).
SELECT COALESCE(a.git_sha, '(sin manifiesto)') AS sha, COALESCE(a.release_tag, '-') AS tag,
       COUNT(*) AS mediciones, COUNT(DISTINCT f.measured_at) AS pasadas
FROM data_freshness_measurement f LEFT JOIN analysis_run a ON a.run_id = f.run_id
GROUP BY 1, 2 ORDER BY MIN(f.measured_at);
