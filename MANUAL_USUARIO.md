# Manual de usuario y operación

**Automatización de Actas de Entrega — Synerjoy BPO**  
**Versión:** primera versión funcional con ambiente de pruebas, reportes y piloto.  
**Actualizado:** 28 de septiembre de 2026.

Este documento describe las funciones que están disponibles hoy y cómo usarlas. El ambiente de pruebas es independiente del productivo. Úsalo para capacitación y para validar cambios antes de operar con información real.

## Respaldos y migraciones

Los respaldos automáticos PostgreSQL quedan en las carpetas `backups\production\` y `backups\test\` dentro de esta carpeta del proyecto. El backend crea y valida un respaldo antes de ejecutar las migraciones en cada inicio; el servicio `backup_scheduler` genera respaldos adicionales cada 24 horas por defecto. Se guardan como archivos `.dump` en formato custom, con la fecha y hora UTC en el nombre. `backups\` está excluida de Git y de las imágenes Docker.

Antes de una intervención manual sobre la base, crea también un respaldo y verifica que el archivo no esté vacío. Conserva una copia cifrada fuera del equipo: los archivos locales no protegen contra la pérdida del disco ni el acceso al equipo. No intercambies respaldos entre producción y pruebas. Para restaurar, detén el backend del entorno y usa solamente su servicio `db` y su propio archivo `.dump`; verifica el nombre de base y el archivo antes de confirmar una restauración, ya que reemplaza datos. En PowerShell, copia el dump al contenedor `db` con `docker compose ... cp` y ejecútalo con `pg_restore` dentro del contenedor; no uses redirección binaria `<` de CMD directamente desde PowerShell.

Para ajustar la frecuencia del servicio automático, define `BACKUP_INTERVAL_SECONDS` en el entorno del proceso Compose (86400 segundos = 24 horas). Si el servicio programador se detiene, revisa sus logs y vuelve a iniciarlo; el backend no ejecutará migraciones si no puede crear y validar primero su respaldo.

## 1. Funciones disponibles

- Inicio de sesión con cuentas creadas por un administrador.
- Roles de Administrador, Técnico, Supervisor uno, Supervisor dos y Auditor.
- Registro y consulta de actas de entrega y cambio de activos.
- Autocompletado de datos a partir de un caso GLPI. En pruebas utiliza casos simulados.
- Registro de cuatro firmas: Recibe, Entrega, Reviso y Aprobo.
- Registro de rechazos con motivo y notificaciones internas.
- Vista previa e impresión del acta y descarga individual en Excel.
- Reportes por periodo, exportación a Excel y PDF, y revisión de comentarios del piloto.
- Interfaz adaptable a computador, tableta y teléfono.

## 2. Perfiles y responsabilidades

| Perfil | Uso principal |
|---|---|
| Administrador | Gestiona usuarios, roles, sedes, actas y configuración desde Django Admin. Puede consultar reportes. |
| Técnico | Registra el acta, valida los datos del activo y participa en las firmas Recibe y Entrega según el flujo. |
| Supervisor uno | Revisa las actas asignadas, registra la firma de revisión o rechaza con motivo. |
| Supervisor dos | Registra la aprobación final de las actas asignadas o rechaza con motivo. |
| Auditor | Consulta información y reportes. |

Las cuentas y sus roles se crean o administran en Django Admin. La ruta es `/admin/`; el acceso requiere una cuenta con permiso de administración. La pantalla del dashboard muestra usuarios y roles, pero su edición se realiza en el Admin.

## 3. Acceso al ambiente de pruebas

El ambiente de pruebas ya está preparado con una base PostgreSQL y volúmenes propios, separados de los del Compose productivo. Abre:

**http://localhost:8001/login/**

La barra amarilla **AMBIENTE DE PRUEBAS** confirma que estás en la instalación aislada. En este ambiente:

- Las notificaciones de correo se escriben en los logs del backend; no se envían a destinatarios reales.
- GLPI opera en modo simulado y las cargas de documentos a GLPI están bloqueadas.
- Los registros y archivos se guardan en volúmenes de pruebas independientes.
- La fecha de cierre del piloto configurada actualmente es el **5 de octubre de 2026**.

Si aún no existe un administrador en esta base, créalo desde PowerShell, ubicado en la carpeta del proyecto:

```powershell
docker compose --env-file .env.test -f docker-compose.test.yml -p actas-test exec backend python manage.py createsuperuser
```

Para volver a iniciar el ambiente después de apagarlo:

```powershell
docker compose --env-file .env.test -f docker-compose.test.yml -p actas-test up -d
```

Para revisar contenedores y logs:

```powershell
docker compose --env-file .env.test -f docker-compose.test.yml -p actas-test ps
docker compose --env-file .env.test -f docker-compose.test.yml -p actas-test logs -f backend
```

Para detenerlo sin borrar la información:

```powershell
docker compose --env-file .env.test -f docker-compose.test.yml -p actas-test down
```

No uses `down -v` salvo que quieras eliminar definitivamente la base y los archivos cargados del ambiente de pruebas. No compartas el archivo `.env.test` ni copies sus claves a producción.

## 4. Crear las cuentas del piloto

Una vez creado el administrador y levantado el ambiente, se pueden crear las tres cuentas con roles asignados. Sustituye los correos de ejemplo por los de los participantes:

```powershell
docker compose --env-file .env.test -f docker-compose.test.yml -p actas-test exec backend python manage.py create_pilot_users --technician-email tecnico@empresa.com --supervisor-one-email supervisor1@empresa.com --supervisor-two-email supervisor2@empresa.com
```

El comando crea estos usuarios:

- `pilot_technician` — Técnico.
- `pilot_supervisor_one` — Supervisor uno.
- `pilot_supervisor_two` — Supervisor dos.

El comando imprime una clave temporal para cada usuario. El administrador debe entregarla por un canal seguro. Se recomienda cambiarla después del primer ingreso. El comando no permite duplicar las cuentas piloto si ya existen; las cuentas se pueden administrar desde Django Admin.

El botón **Reportar problema o sugerencia** aparece mientras `PILOT_MODE=True` y la fecha `PILOT_END_DATE` de `.env.test` no haya vencido. El formulario admite problemas, sugerencias y dudas, y guarda el usuario, la página y la fecha junto al comentario. Los comentarios se revisan en Django Admin, en **Reports → Pilot feedbacks**.

Para cambiar el periodo, edita `.env.test` con la fecha final en formato `AAAA-MM-DD` y recrea el backend:

```powershell
docker compose --env-file .env.test -f docker-compose.test.yml -p actas-test up -d --force-recreate backend
```

## 5. Iniciar sesión y navegar

1. Entra por la dirección del ambiente correspondiente y escribe usuario y contraseña.
2. El **Dashboard** muestra el resumen y las actas visibles para tu rol.
3. Usa **Actas** para buscar por caso, portafolio o tipo y aplicar filtros de estado, tipo y sede.
4. Usa **Revisión** si eres Supervisor uno o Supervisor dos para ver las actas asignadas que esperan tu acción.
5. Abre **Reportes** para revisar métricas o descargarlas.
6. Durante el piloto, usa **Reportar problema o sugerencia** en la barra superior para enviar comentarios al equipo.

## 6. Crear un acta

1. En **Actas**, selecciona **Nueva acta**. Solo el rol Técnico puede crear actas.
2. Completa fecha, sede, tipo (Entrega o Cambio), número de caso GLPI y portafolio.
3. Para cargar datos desde GLPI, escribe el número del caso y pulsa **Autocompletar desde GLPI**. Revisa y corrige los datos antes de guardar.
4. Completa la información de la persona, sistemas, equipo, periféricos, monitor y observaciones que aplique.
5. Acepta las confirmaciones legales requeridas por el formulario y pulsa **Guardar acta**.

Los supervisores no se eligen en el formulario. La configuración global determina Supervisor uno y Supervisor dos; un administrador puede cambiarla en **Django Admin → Configuración de supervisores**. La cuenta del técnico debe tener una firma PNG registrada antes de crear el acta.

En el ambiente de pruebas se pueden usar estos casos simulados: 45084, 42931, 45120, 45200 y 45355. No representan casos productivos. Si el caso ya existe, el número no se puede reutilizar.

## 7. Flujo de firmas y revisión

El flujo usa imágenes PNG registradas por cada firmante; no se dibujan firmas en pantalla. Técnico y supervisores cargan o actualizan su firma desde **Mi firma digital**. La aprobación ocurre en este orden:

| Orden | Firma | Quién la registra | Siguiente paso |
|---|---|---|---|
| 1 | Entrega | Técnico que crea el acta | Bandeja de Supervisor uno |
| 2 | Revisó | Supervisor uno asignado | Bandeja de Supervisor dos |
| 3 | Aprobó | Supervisor dos asignado | Carga final del receptor |
| 4 | Recibe | Receptor asignado, adjuntando el documento firmado | Cierre del proceso |

Las notificaciones internas aparecen en la bandeja y el indicador de notificaciones. En pruebas, los avisos de correo se registran en los logs y no se envían externamente.

Si un supervisor rechaza un acta, debe escribir el motivo y confirmar el rechazo. El motivo queda visible en el detalle y se genera una notificación. El técnico asignado puede corregir y reenviar el acta para que vuelva a la etapa correspondiente.

## 8. Consultar, previsualizar y exportar un acta

Desde la lista o el detalle del acta puedes:

- Abrir el detalle para consultar estado, campos y firmas.
- Consultar la bitácora del acta.
- Abrir la vista previa.
- Descargar el formato individual de acta en Excel.
- Usar la impresión del navegador desde la pantalla de creación como vista previa impresa.

La exportación PDF de la sección **Reportes** corresponde al informe agregado; la descarga individual disponible desde el acta es Excel.

## 9. Reportes

El enlace **Reportes** está disponible para administradores, auditores y supervisores. Puedes indicar fecha inicial y final, aplicar el periodo o limpiar el filtro. El informe presenta:

- Actas registradas y completadas.
- Actas completadas por mes.
- Equipos entregados agrupados por marca y modelo.
- Tiempo promedio en horas desde la creación hasta Recibe, entre Recibe y Entrega, y entre las aprobaciones de cada supervisor. Cuando hay datos, muestra el resultado por firmante.
- Actas pendientes, etapa, responsable y días transcurridos.

Pulsa **Descargar Excel** o **Descargar PDF** para exportar el informe. Los resultados dependen de las fechas y de las firmas registradas; si el ambiente está recién creado, las tablas pueden aparecer vacías.

## 10. Administración habitual

En `/admin/`, el administrador puede gestionar:

- Usuarios y contraseñas.
- Roles y su estado activo.
- Actas, configuración global de supervisores y asignación de técnico.
- Sedes, catálogos de campañas y portafolios, y campos del formulario.
- Firmas y comentarios recibidos del piloto.

Para desactivar una cuenta, desactívala desde Django Admin. No elimines registros de actas o firmas para corregir un flujo: conserva la trazabilidad y utiliza el proceso de revisión disponible.

En **Autenticación y autorización → Usuarios**, abre el usuario para editar nombres, apellidos, correo y, en el formulario relacionado **User role**, su rol, estado del perfil y firma PNG. Guarda con **Guardar**. También puedes seleccionar usuarios en la lista y usar **Desactivar usuarios seleccionados**; la acción no permite desactivar la cuenta administradora que la ejecuta. Para restablecer el acceso, utiliza **Reactivar usuarios seleccionados**.

Las cuentas no se pueden eliminar desde Django Admin. Desactivarlas impide que inicien sesión y que aparezcan como receptores activos, sin borrar sus actas, firmas, eventos ni notificaciones.

Las campañas son un catálogo independiente del campo **Proceso o portafolio**. Administra sus nombres y estado en **Actas → Catálogo de campañas**. Solo las campañas activas se ofrecen al crear o corregir un acta; la campaña seleccionada queda guardada en el acta y aparece en su detalle. El comando `seed_test_campaigns` crea nombres ficticios únicamente en ambientes `test`, `testing` o `staging`; no lo ejecutes en producción.

## 11. Diferencias entre pruebas y producción

El ambiente de pruebas se inicia con `docker-compose.test.yml`, `.env.test` y el proyecto Compose `actas-test`. El ambiente productivo/despliegue principal usa `docker-compose.yml` y `.env`. Ejecuta los comandos de administración usando siempre el mismo Compose y archivo de entorno donde está la cuenta o el acta que quieras gestionar.

En pruebas, el backend fuerza el correo a consola y la integración GLPI a simulación, aunque una variable intente configurarlos de otra manera. Las cargas de documentos a GLPI están bloqueadas. El ambiente puede usarse para capacitación y pruebas sin modificar la base de datos productiva.

## 12. Limitaciones conocidas de esta versión

- La cuenta piloto no recibe una invitación automática: el administrador comunica su usuario y clave temporal.
- Los reportes calculan tiempos con las fechas de firma guardadas; no reconstruyen etapas históricas que no tengan firmas registradas.
- Las dependencias del PDF individual se incluyen en la imagen Docker; en Windows pueden requerirse bibliotecas nativas para usar WeasyPrint.
- Las funciones de respaldo externo, operación offline y sincronización real completa con GLPI siguen fuera del alcance implementado hasta esta versión.

## 13. Ayuda durante el piloto

Ante un problema, anota el número de caso (si aplica), el usuario, la pantalla y los pasos que lo produjeron. Envía el comentario desde **Reportar problema o sugerencia**. No incluyas contraseñas ni tokens en el mensaje. El administrador puede revisar y marcar los comentarios desde Django Admin.
