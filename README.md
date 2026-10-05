# Automatizacion Actas de Entrega

Consulta [MANUAL_USUARIO.md](MANUAL_USUARIO.md) para la guía de uso, operación de pruebas, firmas, reportes y piloto.

Sistema Django para automatizar el Acta de Entrega y Cambio de Activos Tecnologicos de Synerjoy BPO.

## Incluye

- Autenticacion Django y roles de Administrador, Tecnico, Supervisor uno, Supervisor dos y Auditor.
- Modelo configurable para los campos del formulario.
- Catálogos independientes de campañas y procesos/portafolios para las actas.
- Control de duplicados por caso GLPI.
- Flujo separado de firmas: Recibe, Entrega, Reviso y Aprobo.
- Rechazos con motivo obligatorio.
- Bitacora de eventos preparada para auditoria.
- Cliente REST aislado para GLPI.
- SQLite en desarrollo y PostgreSQL mediante variables de entorno.

## Inicio local

Requiere Python 3.12 o superior instalado y disponible como `python`.

```powershell
cd C:\Users\soporte\Documents\automatizacion_actas_entrega
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Abrir `http://127.0.0.1:8000/admin/` para administrar usuarios, roles, sedes y campos configurables.

## Despliegue con Docker

Requiere Docker Engine y Docker Compose v2. Desde la raíz del proyecto:

```powershell
Copy-Item .env.example .env
```

Edita `.env` y cambia `DB_PASSWORD`, `SECRET_KEY` y `DJANGO_SECRET_KEY` por valores aleatorios largos. A continuación construye e inicia los servicios:

```powershell
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f backend
```

El backend escucha en `http://localhost:8000` (o en el valor de `PORT`). Al arrancar aplica `manage.py migrate` y recopila los estáticos. PostgreSQL solo queda expuesto dentro de la red privada `app_network`; sus datos persisten en el volumen `postgres_data`. `init.sql` se ejecuta únicamente al crear por primera vez un volumen vacío. Las tablas propias de la aplicación se crean y actualizan con migraciones Django.

### Publicar una actualización en otro servidor

Para distribuir imágenes, usa un registro accesible desde el servidor (por ejemplo, Docker Hub o un registro privado). Inicia sesión con `docker login` en el equipo que publica y en el servidor. En `.env`, configura `APP_IMAGE` con el mismo nombre y una etiqueta única para esta versión; por ejemplo `docker.io/mi-organizacion/actas:2026-09-29-1`. No guardes contraseñas del registro en el repositorio.

Después de cada cambio de código, desde el proyecto local reconstruye y publica:

```powershell
docker compose build backend
docker compose push backend
```

En el servidor, actualiza `APP_IMAGE` en su `.env` a esa etiqueta y ejecuta:

```powershell
docker compose pull backend
docker compose up -d --no-deps backend
docker compose ps
docker compose logs --tail 100 backend
```

Compose recrea el contenedor con la imagen nueva; la base de datos permanece en `postgres_data` y los archivos cargados en `media_data`. No uses `docker compose down -v` durante actualizaciones, porque `-v` elimina los volúmenes. Conserva las etiquetas anteriores para poder volver a una imagen previa cambiando `APP_IMAGE` y repitiendo `pull` y `up -d`. La imagen de aplicación contiene el código; el `.env` del servidor contiene su configuración y secretos y no se publica junto a la imagen. Las migraciones Django se ejecutan al iniciar el backend.

Para ejecutar migraciones manualmente o abrir una consola SQL:

```powershell
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py showmigrations
docker compose exec db psql -U actas -d actas
```

En `psql`, ejecuta `\dt` para listar tablas y `\q` para salir. Sustituye `actas` si cambiaste `DB_USER` o `DB_NAME` en `.env`. Para crear una cuenta administradora:

```powershell
docker compose exec backend python manage.py createsuperuser
```

Para detener los contenedores sin borrar los datos: `docker compose down`. Para volver a iniciar: `docker compose up -d`.

### Firmas y flujo de aprobación

Solo el rol Técnico puede crear actas. Los supervisores se asignan automáticamente desde **Administración → Configuración de supervisores**; no se eligen en cada acta. El técnico debe tener una firma PNG registrada antes de crear el acta, y cada supervisor carga su propia firma PNG desde **Mi firma digital**. El sistema aplica las firmas estáticas en secuencia: Entrega (técnico), Revisó (Supervisor uno), Aprobó (Supervisor dos) y, al final, el receptor carga el documento firmado/escaneado. No hay captura de firmas dibujadas. Las notificaciones se generan al avanzar o rechazar una revisión.

La carga a GLPI está desactivada por defecto (GLPI_UPLOAD_ENABLED=False). Para habilitarla configura una cuenta/API de GLPI en .env y activa GLPI_UPLOAD_ENABLED=True. Si la asociación falla, se conserva el PDF local y un administrador puede reintentar. Verifica primero el flujo con el GLPI de pruebas de tu organización.

La API REST estándar de GLPI devuelve los datos básicos del ticket. Los campos de persona, cédula, portafolio, sede y activo dependen de las relaciones y campos personalizados configurados en cada instancia; se deben mapear y validar con el esquema del GLPI de destino antes de producción.

## Ambiente aislado de pruebas y piloto

El ambiente de pruebas usa otro archivo Compose, otra base y volúmenes propios, otro puerto (`8001`) y una red independiente. No reutiliza datos, correo ni credenciales GLPI de producción. En PowerShell, crea su archivo de configuración y usa credenciales exclusivas de pruebas:

```powershell
Copy-Item .env.test.example .env.test
notepad .env.test
```

Define contraseñas/clave secretas distintas de producción y establece `PILOT_END_DATE` en formato `AAAA-MM-DD` para el último día del piloto. Deja vacías las variables GLPI y de correo. Inicia el ambiente aislado:

```powershell
docker compose --env-file .env.test -f docker-compose.test.yml -p actas-test build
docker compose --env-file .env.test -f docker-compose.test.yml -p actas-test up -d
docker compose --env-file .env.test -f docker-compose.test.yml -p actas-test logs -f backend
```

Abre `http://localhost:8001`. La barra superior muestra **AMBIENTE DE PRUEBAS**; el backend fuerza correo a consola, GLPI simulado y bloquea cargas a GLPI. Las migraciones se aplican al iniciar. Para apagar solo este entorno: `docker compose --env-file .env.test -f docker-compose.test.yml -p actas-test down`. No uses `down -v` salvo que quieras borrar permanentemente su base y archivos.

En una instalación nueva, crea primero el usuario administrador:

```powershell
docker compose --env-file .env.test -f docker-compose.test.yml -p actas-test exec backend python manage.py createsuperuser
```

Los reportes están en **Reportes** para administradores, auditores y supervisores. Permiten filtrar fechas y descargar Excel o PDF. Las métricas de duración se calculan con las marcas de tiempo de las firmas existentes.

## Respaldos de base de datos

Los despliegues Compose guardan respaldos PostgreSQL en `backups/production/` y `backups/test/` dentro de la carpeta del proyecto. Antes de ejecutar migraciones, el backend genera y valida un respaldo; además, un servicio independiente genera un respaldo cada 24 horas (`BACKUP_INTERVAL_SECONDS`, 86400 por defecto). Los archivos son dumps PostgreSQL en formato custom, con nombres UTC y permisos restrictivos. `backups/` está excluida de Git y de la imagen Docker.

Si ejecutas una migración manual con `manage.py migrate` desde `docker compose exec`, crea primero un respaldo explícito. Ejecuta desde la carpeta del proyecto y usa únicamente el Compose del entorno que vas a modificar:

```powershell
docker compose --env-file .env -f docker-compose.yml exec backend sh /app/scripts/backup_database.sh manual
docker compose --project-name actas-test --env-file .env.test -f docker-compose.test.yml exec backend sh /app/scripts/backup_database.sh manual
```

Para recuperar un respaldo, detén primero el backend del entorno correspondiente y restaura únicamente en la base correcta, después de preservar también su estado actual:

```powershell
$backup = "backups\production\<archivo>.dump"
docker compose --env-file .env -f docker-compose.yml cp $backup db:/tmp/restore.dump
docker compose --env-file .env -f docker-compose.yml exec -T db sh -c 'pg_restore --clean --if-exists --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/restore.dump'
```

En PowerShell, ejecuta los comandos desde la carpeta del proyecto. En pruebas, usa siempre `--env-file .env.test -f docker-compose.test.yml -p actas-test` y el archivo de `backups\test\`. Detén el backend antes de restaurar y no intercambies respaldos entre producción y pruebas. Los respaldos locales no sustituyen una copia cifrada y externa; limita el acceso a la carpeta y copia periódicamente los dumps a almacenamiento protegido fuera del equipo.

Para crear una cuenta piloto para cada rol, ejecuta el comando en el ambiente donde trabajarán los participantes y entrega las claves que imprime por un canal seguro:

```powershell
docker compose --env-file .env.test -f docker-compose.test.yml -p actas-test exec backend python manage.py create_pilot_users --technician-email tecnico@empresa.com --supervisor-one-email supervisor1@empresa.com --supervisor-two-email supervisor2@empresa.com
```

En `.env.test`, activa `PILOT_MODE=True` y define `PILOT_END_DATE` (por ejemplo, una semana después del inicio). Durante ese periodo aparecerá el botón **Reportar problema o sugerencia**. Los comentarios quedan asociados al usuario y se revisan desde el Django Admin, en **Pilot feedbacks**. El comando puede ejecutarse también con `docker compose exec backend ...` si el piloto se realiza en el entorno productivo; las cuentas se crean en la base seleccionada por ese comando.

## Autocompletado GLPI simulado

En desarrollo local el autocompletado usa cinco casos ficticios cuando `GLPI_SIMULATION_MODE=True` en `.env`:

- `45084`
- `42931`
- `45120`
- `45200`
- `45355`

En la pantalla **Nueva acta**, escribe uno de esos números y pulsa **Autocompletar desde GLPI**. El sistema carga usuario, documento, portafolio, sede, tipo de acta, equipo, usuario de Windows, correo, acceso a HelpDesk y periféricos ficticios.

Para conectarlo al servidor real, cambia `GLPI_SIMULATION_MODE=False` y configura `GLPI_BASE_URL`, `GLPI_APP_TOKEN` y `GLPI_USER_TOKEN`. La vista y el indicador de carga permanecen iguales; solo cambia la fuente de datos.

## Endpoints de firma

- `POST /api/actas/{public_id}/receive/sign/`
- `POST /api/actas/{public_id}/delivery/sign/`
- `POST /api/actas/{public_id}/review/approve/`
- `POST /api/actas/{public_id}/review/reject/`
- `POST /api/actas/{public_id}/final-approval/approve/`
- `POST /api/actas/{public_id}/final-approval/reject/`

## Vista previa y supervisores

La vista previa del acta nueva se genera con los datos del formulario y no guarda ni crea el acta. Incluye la estructura del documento y muestra pendientes las firmas que todavía no corresponden. Las vistas de detalle y revisión muestran los datos guardados y las firmas registradas.

Los supervisores se asignan globalmente a actas nuevas. Tras aplicar migraciones, se usan las cuentas activas carlos (Supervisor uno) y jaime (Supervisor dos), si tienen los roles correspondientes. Un administrador puede cambiar la asignación en Django Admin, sección **Configuración de supervisores**. El cambio afecta actas nuevas; las existentes conservan sus asignaciones.
