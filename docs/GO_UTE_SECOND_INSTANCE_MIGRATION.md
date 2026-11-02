# G.O. como segunda instancia del mismo IAchat — auditoría y corte seguro

**Estado:** candidato de código, NO desplegado. El G.O. existente en `go-ute.duckdns.org` debe seguir intacto hasta que un E2E real apruebe la sustitución. No ejecutar migraciones destructivas ni importar automáticamente registros de octubre.

## Evidencia inspeccionada el 30/10/2026

- IAchat: `iachat/app.py` expone chat, adjuntos, historial, memorias, búsquedas y archivos; `iachat/store.py` persiste usuarios, conversaciones, imágenes y memorias en SQLite, con dueño por registro. `iachat/backend.py` implementa tanto `ProviderBackend` (minirouter integrado) como `RouterFirstBackend`.
- La ruta `iachat/structured_data.py::handle` **crea, modifica y borra registros SQLite sin confirmación**. No debe convertirse en el registro oficial de G.O. Este cambio la desactiva sólo cuando `IACHAT_PROFILE=go-ute`; la instancia personal no cambia. El perfil laboral puede conversar, pero **aún no registra novedades oficiales**.
- G.O. existente: `go_ute/db.py` usa `GO_DATABASE_URL` PostgreSQL; `go_ute/flexible.py` propone cambios JSONB y confirma mediante transacción; `go_ute/app.py` mantiene passkeys, historial y documentos. El Router grande sigue siendo una dependencia separada, no se copia ni despliega desde este cambio.
- Archivo de referencia encontrado: `Seguimiento_Integral_Obras_y_Personal_actualizado_26-10-2026.xlsx`, **22 hojas** (no 18 en esa versión): OBRAS, PARTE DIARIO, PERMISOS, MOVIMIENTOS, RESUMEN, RECURSOS, VALLADOS, FUNDICION, ACTIVIDADES EXTERNAS, INCIDENCIAS, NOTAS ACTUALIZACION, PERSONAL UTE, ROTACIONES PERSONAL, EXTRAS CANALETAS, CONTROL SUMIDEROS, REGLAS DE CONTROL, PENDIENTES DE VERIFICAR, INDICE INTEGRAL, CRONOLOGIA 20-21 OCT, CRONOLOGIA 22-24 OCT, NOVEDADES 22-24 OCT, PLANIFICACION 25-27 OCT. Es referencia funcional, **no datos para importar**.

### Campos de la planilla comprobados (no importar)

- **OBRAS**, fila 3: Pto., Dirección, Contratista, Puntero, Estado, Permiso vigente, Vence, Requiere asfalto, Juntas con brea líquida, Demarcación horizontal.
- **PARTE DIARIO**, fila 3: Fecha, Pto., Dirección, Contratista, Puntero, Personal, Estado del día, Trabajo ejecutado, Observaciones, Dotación / recurso compartido.
- **PERMISOS**, fila 3: Pto., Dirección / alcance, ID permiso, Fecha inicio permiso, Fecha fin permiso, Estado / nota.
- **MOVIMIENTOS**, fila 3: Fecha, Contratista origen, Contratista destino, Recurso / equipo, Motivo, Observaciones.
- **VALLADOS**, fila 1: Pto., Dirección, Contratista, Finalización, Retiro previsto / realizado, Estado del vallado.
- **FUNDICION**, fila 1: Pto., Dirección, Movimiento, Tipo de fundición, Elemento, Cantidad, Clasificación / Procedencia.
- **PLANIFICACION 25-27 OCT**, fila 2: Fecha, Contratista, Pto. / Lugar, Tipo de registro, Detalle / condición.

Estos campos orientan consultas y propuestas, no justifican copiar filas, generar tablas nuevas ni asumir que PostgreSQL productivo tiene la misma estructura.

## Decisión: mismo código, dos procesos y datos separados

| Alternativa | Evaluación |
|---|---|
| Copiar interfaz/backend de IAchat a G.O. | Rechazada: dos copias divergen y duplican correcciones |
| G.O. como conversación dentro del IAchat personal | Rechazada: mezcla de identidades, datos y sesiones |
| **Mismo paquete IAchat, segunda instancia aislada** | **Elegida:** misma UI/memoria/adjuntos/búsqueda/motor, configuración y datos propios |
| Reescribir ambos sobre un framework nuevo | Rechazada: costo y riesgo sin mejorar primera conversación |

La instancia personal conserva su servicio, SQLite, credenciales y dominio. La instancia laboral deberá usar **otro** proceso, dominio, `IACHAT_DB` persistente, secreto de sesión, usuarios/OIDC y configuración de proveedores; su PostgreSQL laboral sigue separado. No montar el volumen SQLite personal en G.O., no copiar el fichero de usuarios ni usar un proxy que comparta cookies entre hosts. Los archivos y memorias de trabajo residen en el SQLite laboral hasta que se defina, con evidencia, si conviene moverlos a PostgreSQL. **No afirmar que ya están migrados.**

## Barreras de arranque verificables

En el perfil `go-ute`, el proceso falla antes de abrir SQLite si falta `IACHAT_DB` con **ruta absoluta explícita** o si `IACHAT_AUTH_SECRET` tiene menos de 32 caracteres. La instancia personal conserva sus valores existentes. La ruta absoluta y la longitud del secreto **no demuestran por sí mismas** que sean distintos de los de IAchat personal: comparar destinos y secretos sin imprimirlos antes de arrancar en Oracle.

**Cookies de sesión separadas por perfil (31/10):** la firma HMAC de G.O. incluye el namespace `go-ute:`; IAchat personal mantiene exactamente la firma previa para no cerrar sesiones existentes. Incluso si se reutilizaran por error el secreto y el nombre de usuario, una cookie de G.O. no se valida en IAchat personal ni viceversa. Esto es defensa adicional, **no reemplaza** configurar secretos distintos, orígenes distintos, cookies host-only, bases y volúmenes independientes. Pruebas offline cubren ambos sentidos y el callback OIDC laboral. No se ha probado en Oracle ni desplegado.

**Autorización Google laboral:** el callback OIDC de G.O. exige `IACHAT_GOOGLE_ALLOWED_SUBS`, una lista explícita de identificadores `sub` verificados de Google, separados por comas. Sin lista o si el `sub` no figura, devuelve 403 **antes** de crear usuarios. No usar correos electrónicos como identidad ni reutilizar una lista personal. El perfil IAchat personal conserva su comportamiento anterior. Esta barrera es código candidato y aún no constituye prueba de OIDC en Oracle. No usar la misma ruta, el mismo volumen ni el mismo secreto. Una memoria persistente no puede sustituir las instrucciones de no escribir datos oficiales sin aprobación.

## Secuencia mínima, sin tocar producción antes de tiempo

1. Inspeccionar en Oracle, sólo lectura y sin imprimir secretos: rutas reales de servicios, SHA de ambos despliegues, discos/volúmenes, esquema y recuentos de tablas PostgreSQL existentes; inventariar backup y restauración. Confirmar separación de orígenes, cookies, OIDC y WebAuthn. Este repositorio no demuestra esos hechos.
2. Arrancar en entorno aislado la misma revisión de IAchat con `IACHAT_PROFILE=go-ute`, SQLite laboral nuevo, usuarios de prueba y el backend ya existente. **No** copiar credenciales personales. El minirouter integrado se puede ensayar **únicamente después de comprobar la cuenta y el modelo gratuito concretos**, sin pagos ni overages; la allowlist del código por sí sola no prueba gratuidad. Si no hay verificación, sólo backend simulado/offline.
3. Reusar la **lógica existente** de G.O. para lectura de obras, propuesta, confirmación y auditoría contra el PostgreSQL ya instalado; no duplicar tablas ni crear un segundo libro mayor SQLite. Antes de implementar el puente, comprobar columnas y constraints reales. El adaptador debe operar con identidad laboral autenticada y permiso mínimo, no con cookies del IAchat personal. La aprobación debe vincularse a una propuesta y quedar transaccionalmente auditada.
4. E2E en instancia laboral: conversación real autorizada → novedad **propuesta** → confirmación → consulta PostgreSQL → cierre de sesión → nueva sesión → recuperación de historial y novedad. Además: usuarios cruzados, adjuntos, memoria, origen, cookies y solicitudes sin autorización; fallo de proveedor no debe crear registros.
5. Sólo después de backup verificado, E2E y rollback probado, hacer cutover de `go-ute.duckdns.org` por GitHub Actions + SSH. Conservar la versión G.O. anterior para restauración. Eliminar la duplicación **después**, no antes, de comprobar funcionamiento.

## Bloqueos explícitos

- Falta lectura real del esquema PostgreSQL y del estado Oracle actual; los archivos del repositorio no prueban qué está desplegado.
- No se verificó que las cuentas y modelos del minirouter sean gratuitos sin posibilidad de cargo. **No hay autorización para inferencia externa ni para promover Router PR #87**.
- La UI y autenticación IAchat no equivalen automáticamente a las passkeys actuales de G.O.; preservar acceso y usuarios durante el piloto, no hacer reemplazo silencioso.
- Este PR sólo incorpora el aislamiento del camino de escritura SQLite y pruebas offline. **No es una entrega E2E ni una migración productiva.**

## Adaptador mínimo de lectura oficial (31/10, candidato sin despliegue)

Se añadió `iachat/go_work_context.py` al **mismo** motor IAchat, sin copiar el backend de G.O. ni crear tablas. Para una o varias obras identificadas explícitamente (por ejemplo `obra 1093` o `compará obra 1093 con obra 1190`), consulta `obras` y hasta ocho eventos oficiales vigentes **por obra** de `go_record_events`, excluyendo correcciones reemplazadas; incluye dirección y estado oficial. Se admiten hasta ocho presupuestos por consulta. La consulta usa parámetros SQL y una transacción `READ ONLY`. Los datos se incluyen como evidencia de herramienta, **nunca como instrucciones del sistema**. Con varias obras explícitas entrega los datos separados por presupuesto, sin elegir una arbitrariamente; más de ocho presupuestos se rechazan.

La conexión requiere `GO_WORK_READONLY_DSN` **diferente de** `GO_DATABASE_URL`, correspondiente a un rol PostgreSQL con SELECT y **sin** INSERT/UPDATE/DELETE sobre `obras`, `go_record_types`, `go_record_proposals`, `go_record_events` y `go_chat_turns`. La aplicación rechaza incluso un rol escritor aunque la transacción haya sido marcada READ ONLY. No imprimir la DSN ni compartirla con la instancia personal. La configuración de rol se hará sólo tras auditar PostgreSQL real y sus permisos; este cambio no crea roles, no ejecuta DDL y no modifica Oracle.

Si se menciona una obra y falta la conexión, hay error 503 antes de inferencia: **no** se presenta una conjetura como dato oficial. La conversación general sin presupuesto explícito sigue usando el motor de IAchat. Esta lectura **no** implementa propuestas ni confirmaciones: para eso sigue siendo necesario conectar de forma autenticada la lógica transaccional existente de G.O. sin duplicar esquemas.

Pruebas nuevas offline: SELECT parametrizado, transacción de solo lectura, rechazo de rol escritor, obra ambigua, ausencia de DSN, evidencia aislada del rol system y bloqueo de inferencia ante falla de PostgreSQL. **No equivalen a una prueba real de Oracle ni a conversación con proveedor gratuito.** No desplegar antes de comprobar tablas, rol, aislamiento y rollback.

## Revisión de compatibilidad y privilegios — 31/10

La migración fuente de G.O. `migrations/001_initial.sql` declara `obras(id,presupuesto,direccion,estado)`; `migrations/005_flexible_records.sql` declara `go_record_events(id,tipo,version,obra_id,datos,reemplaza,creado)` y sus referencias. La consulta de lectura ahora incluye **`obras.estado`**: antes faltaba el estado en preguntas sobre una obra concreta. Esto verifica compatibilidad con **el código fuente**, no con el esquema instalado en Oracle.

El rol SELECT también se rechaza si conserva `CREATE` a nivel de **base de datos**, aunque no tenga INSERT/UPDATE/DELETE en tablas ni CREATE en los esquemas existentes: con ese privilegio podría crear un esquema nuevo. Se añadió una regresión offline. El adaptador sigue sin escribir ni crear roles; falta inspeccionar los privilegios reales en Oracle. No se habilitaron modelos externos ni se cambió la instancia laboral productiva.


## Barrera económica del perfil laboral (31/10, rama candidata)

La selección de backend ahora es **fail closed** para `IACHAT_PROFILE=go-ute`:
si `IACHAT_BACKEND` no es exactamente `router`, `get_backend()`
rechaza el intento con `go_router_only_until_free_models_verified`.
`/ready` responde HTTP 503 en ese caso. Esto evita que una segunda
instancia herede por accidente las claves Groq/OpenRouter/NVIDIA de IAchat
personal y haga inferencias directas, incluso cuando los nombres de modelos
aparezcan en una allowlist. La instancia personal no cambia.

El transporte Router de G.O. sigue restringido a `127.0.0.1:8010`
o `localhost:8010` sin proxy, redirecciones ni fallback a proveedor.
**No es una prueba de gratuidad del Router:** verificar los modelos y las
condiciones de facturación de las cuentas antes de activar inferencia.
No desplegar la instancia laboral hasta validar esa condición y el E2E real.


## Adaptador de propuestas en el chat compartido (31/10, candidato no desplegado)

`iachat/go_work_actions.py` **no implementa otro motor de IA**: interpreta la salida JSON de la misma llamada al backend de IAchat y delega la validación, preparación y confirmación en `go_ute.flexible`, el código original de G.O. y sus tablas `go_record_proposals`, `go_record_events` y `go_record_types`. El JSON de un modelo **no es autorización de escritura**. Las propuestas sólo se preparan; un mensaje posterior explícito `Confirmo propuesta UUID` o `Descarto propuesta UUID` resuelve la decisión.

El adaptador está **desactivado por defecto** y exige simultáneamente `IACHAT_PROFILE=go-ute`, `GO_WORK_WRITE_ENABLED=1`, `GO_DATABASE_URL` laboral y el paquete original `go_ute` instalado en el proceso de trabajo. Nunca habilitarlo en IAchat personal. El permiso de escritura de la conexión laboral y los privilegios del usuario autenticado deben auditarse antes de habilitar producción; **no** reutilizar la DSN de solo lectura ni credenciales personales. Los adjuntos no pueden preparar escrituras con este puente: su clasificación/asociación requiere una fase específica y confirmación.

La autorización de cada propuesta está vinculada al **último mensaje de asistente de la conversación autenticada**. `ConversationStore` conserva el identificador UUID canónico emitido por el servidor al recargar la conversación; la confirmación no acepta IDs de otra conversación, ni IDs anteriores, ni el fallback global de turnos de G.O. Esto limita la confirmación a la sesión conversacional correcta, sin cambiar el esquema PostgreSQL. La auditoría existente conserva el origen, propuesta, versión y corrección, pero todavía **no** registra explícitamente el usuario IAchat en cada evento oficial; resolver antes de autorizar multiusuario productivo.

La prueba integrada se ejecuta en PostgreSQL 16 efímero con migraciones G.O. reales, login Google simulado, chat HTTP y Router **simulado**. Verifica propuesta sin evento, rechazo de UUID entre conversaciones, confirmación transaccional, lectura posterior, rechazo de obra contradictoria y no duplicación. **No** demuestra inferencia externa, acceso Oracle, despliegue, separación productiva ni autorización de modelos gratuitos. No hacer cutover ni activar `GO_WORK_WRITE_ENABLED` en Oracle antes de comprobar todos esos puntos.


## Bloqueo adicional de inferencia externa — 1/11 (candidato, no desplegado)

En la segunda instancia, `IACHAT_BACKEND=router`, una URL loopback y un token
**ya no bastan** para enviar solicitudes: `GO_ROUTER_INFERENCE_ENABLED=1`
debe habilitarse explícitamente **sólo después** de auditar el catálogo,
la política de selección y las condiciones de la cuenta del Router instalado.
Sin ese valor exacto, `/ready` devuelve 503, `/api/router/status`
indica `go_router_inference_not_authorized` y el transporte no llama a
`/route`. Es un cierre por defecto; la variable **no certifica** por sí sola
gratuidad ni elimina el control económico independiente de Router.
Las pruebas offline pueden usar la variable con Router simulado, sin inferencia
externa ni proveedores facturables. No activar esta variable en Oracle sin
evidencia real de modelos gratuitos autorizados y ausencia de riesgo de cobro.
