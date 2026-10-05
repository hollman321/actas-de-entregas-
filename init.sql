-- PostgreSQL ejecuta este archivo solo al inicializar un volumen de datos vacío.
-- Django crea y versiona las tablas funcionales con `manage.py migrate` al arrancar.
CREATE TABLE IF NOT EXISTS deployment_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO deployment_metadata (key, value)
VALUES ('schema_owner', 'django-migrations')
ON CONFLICT (key) DO NOTHING;
