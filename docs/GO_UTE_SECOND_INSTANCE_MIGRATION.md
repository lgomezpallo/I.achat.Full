# G.O. como segunda instancia del mismo IAchat — auditoría y corte seguro

**Estado:** candidato de código, NO desplegado. El G.O. existente en `go-ute.duckdns.org` debe seguir intacto hasta que un E2E real apruebe la sustitución. No ejecutar migraciones destructivas ni importar automáticamente registros de octubre.

## Evidencia inspeccionada el 30/10/2026

- IAchat: `iachat/app.py` expone chat, adjuntos, historial, memorias, búsquedas y archivos; `iachat/store.py` persiste usuarios, conversaciones, imágenes y memorias en SQLite, con dueño por registro. `iachat/backend.py` implementa tanto `ProviderBackend` (minirouter integrado) como `RouterFirstBackend`.
- La ruta `iachat/structured_data.py::handle` **crea, modifica y borra registros SQLite sin confirmación**. No debe convertirse en el registro oficial de G.O. Este cambio la desactiva sólo cuando `IACHAT_PROFILE=go-ute`; la instancia personal no cambia. El perfil laboral puede conversar, pero **aún no registra novedades oficiales**.
- G.O. existente: `go_ute/db.py` usa `GO_DATABASE_URL` PostgreSQL; `go_ute/flexible.py` propone cambios JSONB y confirma mediante transacción; `go_ute/app.py` mantiene passkeys, historial y documentos. El Router grande sigue siendo una dependencia separada, no se copia ni despliega desde este cambio.
- Archivo de referencia encontrado: `Seguimiento_Integral_Obras_y_Personal_actualizado_26-10-2026.xlsx`, **22 hojas** (no 18 en esa versión): OBRAS, PARTE DIARIO, PERMISOS, MOVIMIENTOS, RESUMEN, RECURSOS, VALLADOS, FUNDICION, ACTIVIDADES EXTERNAS, INCIDENCIAS, NOTAS ACTUALIZACION, PERSONAL UTE, ROTACIONES PERSONAL, EXTRAS CANALETAS, CONTROL SUMIDEROS, REGLAS DE CONTROL, PENDIENTES DE VERIFICAR, INDICE INTEGRAL, CRONOLOGIA 20-21 OCT, CRONOLOGIA 22-24 OCT, NOVEDADES 22-24 OCT, PLANIFICACION 25-27 OCT. Es referencia funcional, **no datos para importar**.

## Decisión: mismo código, dos procesos y datos separados

| Alternativa | Evaluación |
|---|---|
| Copiar interfaz/backend de IAchat a G.O. | Rechazada: dos copias divergen y duplican correcciones |
| G.O. como conversación dentro del IAchat personal | Rechazada: mezcla de identidades, datos y sesiones |
| **Mismo paquete IAchat, segunda instancia aislada** | **Elegida:** misma UI/memoria/adjuntos/búsqueda/motor, configuración y datos propios |
| Reescribir ambos sobre un framework nuevo | Rechazada: costo y riesgo sin mejorar primera conversación |

La instancia personal conserva su servicio, SQLite, credenciales y dominio. La instancia laboral deberá usar **otro** proceso, dominio, `IACHAT_DB` persistente, secreto de sesión, usuarios/OIDC y configuración de proveedores; su PostgreSQL laboral sigue separado. No montar el volumen SQLite personal en G.O., no copiar el fichero de usuarios ni usar un proxy que comparta cookies entre hosts. Los archivos y memorias de trabajo residen en el SQLite laboral hasta que se defina, con evidencia, si conviene moverlos a PostgreSQL. **No afirmar que ya están migrados.**

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
