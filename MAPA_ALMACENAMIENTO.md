# Mapa de almacenamiento y base de datos

Este documento describe el despliegue Docker principal del proyecto. No incluye
contraseñas ni otros secretos de `.env`.

## PostgreSQL de despliegue

Desde la carpeta raíz del proyecto, la configuración principal es
`docker-compose.yml` más `.env`. Con los valores actuales/defaults:

| Parámetro | Valor |
|---|---|
| Servicio Compose | `db` |
| Host PostgreSQL dentro de la red Docker | `db` |
| Puerto PostgreSQL dentro de Docker | `5432` |
| Base de datos | `actas` (variable `DB_NAME`) |
| Usuario | `actas` (variable `DB_USER`) |
| Persistencia | Volumen Docker `automatizacion_actas_entrega_postgres_data` |
| Directorio PostgreSQL dentro del contenedor | `/var/lib/postgresql/data` |

El servicio PostgreSQL no publica un puerto en el host en la configuración
principal; se accede desde los contenedores en la red `app_network`. Para abrir
una consola SQL desde PowerShell:

```powershell
docker compose --env-file .env -f docker-compose.yml exec db psql -U actas -d actas
```

Si `DB_USER` o `DB_NAME` difieren de `actas`, usa sus valores de `.env`. No
compartas ese archivo. En `psql`, `\dt` lista las tablas y `\q` cierra la
consola.

## Tablas PostgreSQL

Las tablas se crean y actualizan mediante migraciones Django. El inventario
siguiente se contrastó con las tablas existentes en PostgreSQL de producción.

| Tabla | Contenido |
|---|---|
| `actas_acta` | Registro principal: caso GLPI, fecha, sede, campaña, portafolio, creador, técnico asignado, receptor, supervisores, estado, consentimientos legales, ruta del PDF firmado y estado de carga a GLPI. |
| `actas_actafieldvalue` | Valores de cada campo configurable por acta, vinculados con su definición; incluye fuente y usuario que actualizó el dato. |
| `actas_signature` | Firmas y rechazos: tipo/etapa, firmante, fecha, resultado, motivo, hash, método y ruta de la imagen PNG cuando aplica. La recepción final registra el hash del PDF escaneado y método `SCANNED_PDF`. |
| `actas_formfielddefinition` | Definiciones de los campos dinámicos del formulario, sección, tipo, opciones, obligatoriedad y estado. |
| `actas_campaigncatalog` | Catálogo de campañas y relación al portafolio. |
| `actas_portfoliocatalog` | Catálogo de portafolios y valores predeterminados JSON para campos de sistemas/usuarios. |
| `actas_site` | Catálogo de sedes. |
| `accounts_userrole` | Rol activo por usuario y ruta de su firma PNG estática de perfil. |
| `accounts_workflowconfig` | Supervisores globales asignados y datos de actualización de esa configuración. |
| `notifications_notification` | Notificaciones internas persistentes: destinatario, acta, título, mensaje, nivel, fecha y estado de lectura. |
| `audit_actaevent` | Bitácora de eventos de actas: acción, actor, estados anterior/nuevo, motivo, metadatos, IP y fecha. |
| `reports_pilotfeedback` | Comentarios, problemas y sugerencias del piloto, autor, página y estado de revisión. |
| `auth_user` | Cuentas Django, datos de autenticación, banderas de acceso, nombres y correo. Los hashes de contraseña se guardan aquí; no se almacenan contraseñas en texto plano. |
| `auth_group` | Grupos de permisos de Django. |
| `auth_permission` | Permisos Django registrados por aplicación/modelo. |
| `django_content_type` | Registro de modelos/aplicaciones usado por permisos y administración. |
| `django_admin_log` | Historial de acciones realizadas desde Django Admin. |
| `django_session` | Sesiones de usuarios cuando el backend de sesiones está configurado en base de datos. |
| `django_migrations` | Historial de migraciones aplicadas (tabla mantenida por Django). |
| `auth_user_groups` | Relación muchos-a-muchos entre usuarios y grupos Django. |
| `auth_user_user_permissions` | Permisos Django asignados directamente a usuarios. |
| `auth_group_permissions` | Permisos Django asociados a grupos. |
| `deployment_metadata` | Metadatos de despliegue inicializados por `init.sql`. |

## Archivos y volúmenes Docker

Las rutas de archivos de la aplicación son rutas relativas a `MEDIA_ROOT`
(`/app/media` dentro del contenedor backend). En el Compose principal ese
directorio persiste en el volumen `automatizacion_actas_entrega_media_data`.

| Tipo de archivo | Ruta relativa a `MEDIA_ROOT` | Ejemplo de ruta en el contenedor |
|---|---|---|
| Firma PNG de perfil técnico/supervisor | `supervisor-signatures/` | `/app/media/supervisor-signatures/<archivo>.png` |
| Copia de firma asociada a una firma de acta | `signatures/YYYY/MM/` | `/app/media/signatures/<año>/<mes>/signature-<id>.png` |
| Imagen de firma de rechazo | `signatures/YYYY/MM/` | `/app/media/signatures/<año>/<mes>/signature-rejected-<id>.png` |
| PDF firmado/escaneado cargado por el receptor | `actas/YYYY/MM/` | `/app/media/actas/<año>/<mes>/<archivo>.pdf` |

Las tablas guardan el nombre/ruta relativa del archivo; el contenido binario
permanece en el volumen de medios, no en una columna PostgreSQL.

El volumen `automatizacion_actas_entrega_static_data` se monta en
`/app/staticfiles` para los recursos estáticos recopilados. No contiene datos de
actas ni firmas.

Los respaldos PostgreSQL se guardan en la carpeta del proyecto
`backups\production\` y `backups\test\`; el directorio del host se monta como
`/backups` en los contenedores correspondientes. Son archivos `.dump`, separados
por entorno. No copies los respaldos de producción al entorno de pruebas.

## PDF y notificaciones

- La vista previa PDF del acta se renderiza al solicitarla y se transmite al
  navegador; no se guarda como archivo hasta que se carga el PDF firmado por el
  receptor. Los reportes PDF también se generan para descarga y no se persisten
  en PostgreSQL.
- El PDF final firmado que carga el receptor se almacena como archivo bajo
  `actas/YYYY/MM/`; su referencia y estado quedan en `actas_acta.pdf_file` y
  `actas_acta.status`.
- Las notificaciones del centro interno se guardan en `notifications_notification`.
  Una notificación de entrega va al Supervisor uno y la aprobación del
  Supervisor uno genera la notificación para Supervisor dos.
- La configuración actualmente observada en el contenedor principal usa
  `django.core.mail.backends.console.EmailBackend`. Por ello el sistema escribe
  los correos en los logs del backend, no los entrega a buzones externos. Para
  correo real hay que configurar un backend SMTP y credenciales en `.env`, sin
  publicarlas en este documento. La fila de notificación interna se conserva en
  PostgreSQL aunque el correo externo no esté habilitado.

## Ubicación del proyecto y acceso SQL

La carpeta raíz del proyecto contiene los archivos de configuración y código.
PostgreSQL persiste en el volumen Docker nombrado arriba, no en un archivo
`.db` dentro de esa carpeta. Para ver la ubicación interna gestionada por Docker:

```powershell
docker volume inspect automatizacion_actas_entrega_postgres_data
```

No edites directamente los archivos internos del volumen. Consulta o modifica
los datos usando `psql`, Django Admin o comandos Django apropiados.
