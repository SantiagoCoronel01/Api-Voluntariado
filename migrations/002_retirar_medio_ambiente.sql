-- Select the application's database and take a backup before running.
-- Existing announcements keep their IDs, dates, images and descriptions.
UPDATE anuncios
SET tipo_evento = 'Información'
WHERE tipo_evento = 'Medio Ambiente';
