# Sesiones y permisos

La API requiere `Authorization: Bearer <token>` en sus operaciones. El token se entrega al iniciar sesión, está firmado con ItsDangerous y vence a las 12 horas, o a los 30 días con `recordarme: true`. Cada token tiene un identificador aleatorio cuyo hash se guarda en `sesiones_usuario`. El estado, el perfil y la vigencia de esa sesión se consultan en la base en cada solicitud; el cliente no decide sus permisos.

`POST /cerrar_sesion` revoca la sesión actual. Cambiar contraseña, perfil, correo o estado revoca las sesiones del usuario afectado; desactivar y reactivar una cuenta no recupera sus tokens anteriores. Las contraseñas nuevas se guardan como hashes scrypt con sal y se validan también en el servidor. El login convierte una credencial antigua en hash dentro de la misma transacción que emite la sesión, pero debe ejecutarse además la migración masiva para cubrir cuentas que no ingresen.

| Operación | Voluntario | Referente / administrador |
| --- | --- | --- |
| Ver anuncios y calendario | Sí | Sí |
| Crear, editar o borrar anuncios / eventos | No | Sí |
| Consultar inventario | Sí | Sí |
| Modificar inventario | No | Sí |
| Crear una sesión y guardar su asistencia | Sí, como autor autenticado | Sí |
| Consultar registros de asistencia | Sí | Sí |
| Corregir o borrar registros guardados | No | Sí |
| Gestión de usuarios, proyectos y destinatarios | No | Sí |

El voluntario no puede utilizar `guardar_asistencia` para agregar datos a sesiones ajenas ni para reescribir una asistencia ya guardada. Repetir exactamente los mismos DNI y estados devuelve éxito sin duplicarlos, para poder reintentar si se perdió la respuesta. Una solicitud con estados diferentes se rechaza. El autor de sesiones y anuncios se toma del token, aunque el cuerpo envíe otro usuario. No se permite desactivar, eliminar o quitar el rol al último administrador o referente activo; la comprobación bloquea las filas durante la transacción para serializar cambios concurrentes.

Una cuenta deshabilitada o eliminada obtiene HTTP 403 y `codigo: cuenta_deshabilitada`. La app elimina su sesión y muestra «Su cuenta se deshabilitó. Contacte a un administrador.». El servidor rechaza la siguiente solicitud inmediatamente; la app también verifica al navegar, al volver del segundo plano y cada 15 segundos mientras está visible. Sin conexión, la app bloquea la interacción hasta verificar nuevamente.

## Activar los cambios en Railway

1. Generar una clave aleatoria en una terminal local:

   ```powershell
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

2. En las variables del servicio de API en Railway, guardar ese valor como `SECRET_KEY`. No incluirlo en Git, el APK ni el frontend. Usar la misma clave en todas las réplicas y reinicios. Cambiarla invalida todos los tokens existentes.
3. **Antes de desplegar, aplicar la migración descrita abajo.** Esta versión necesita cambios de esquema. Coordinar una ventana sin escrituras y probar primero con una copia de la base.
4. Desplegar todos los módulos Python de este repositorio y `requirements.txt`, no solo `app.py` y `seguridad.py`. Después compilar e instalar la app Ionic con `npm run android:apk`. Los tokens anteriores usan otro formato y deben iniciar sesión nuevamente; coordinar la actualización con los usuarios.
5. Iniciar sesión nuevamente. Las sesiones locales anteriores no cuentan como autenticación del servidor.
6. Verificar con una cuenta de cada rol. Desactivar una cuenta que esté abierta en otro dispositivo y comprobar el aviso y el cierre. No hacerlo con la única cuenta administradora activa.

Si falta `SECRET_KEY`, el servidor responde 503 en login y operaciones privadas, sin recurrir a una clave predeterminada. `/sesion_actual` devuelve únicamente los datos públicos del usuario autenticado y no se almacena en caché. El listado de usuarios tampoco devuelve contraseñas.

El registro público solo acepta perfiles voluntario y referente; ambos quedan pendientes de activación. La creación de administradores requiere un gestor autenticado. Login, registro público, imágenes publicadas y preflight CORS siguen disponibles sin sesión.

## Pruebas sin base real

```powershell
python -m unittest discover -v
```

Las pruebas sustituyen MySQL por un doble y no modifican cuentas ni datos reales. Requieren Flask y Flask-Cors; en Windows también se necesita `tzdata` para las fechas de asistencia. Las pruebas del cliente están en `ionic_v1/src/app/autenticacion.spec.ts`, junto a las de rutas y vistas.

## Migración obligatoria de base de datos

Esta migración no se ejecuta al iniciar la API. No se aplicó a Railway durante las correcciones locales.

1. Respaldar la base y comprobar su restauración en un entorno de prueba. Confirmar que las tablas de la aplicación usan InnoDB: los bloqueos y las transacciones de cuentas, inventario y asistencias requieren ese motor. Detener las escrituras durante la migración y la conversión de contraseñas. MySQL confirma los cambios DDL automáticamente: un `ROLLBACK` no deshace los `ALTER TABLE`.
2. Conectarse con el cliente MySQL a la base elegida. Pedir la contraseña con `-p`, sin escribirla en la línea de comandos:

   ```powershell
   mysql -h HOST -u USUARIO -p NOMBRE_BASE
   ```

   Dentro del cliente MySQL, ejecutar el archivo de este repositorio (adaptar la ruta si corresponde):

   ```sql
   SOURCE C:/Users/SANT/Api-Voluntariado/migrations/001_seguridad_y_descripciones.sql;
   SHOW COLUMNS FROM usuario;
   SHOW COLUMNS FROM anuncios;
   SHOW TABLES LIKE 'sesiones_usuario';
   SHOW TABLES LIKE 'operaciones_idempotentes';
   ```

   El archivo amplía `usuario.clave` a 255 caracteres y `mail` a 254; amplía el título a 150 y convierte `anuncios.descripcion` a `TEXT` con utf8mb4. Crea las tablas de sesiones e idempotencia. No cambia roles ni estados. Revisar el esquema real antes de aplicarlo, especialmente valores nulos y restricciones existentes.
3. Con las variables `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` ya configuradas en el entorno del servidor, instalar las dependencias y convertir las credenciales. Ejecutar desde la carpeta de la API:

   ```powershell
   python -m pip install -r requirements.txt
   python migrar_credenciales.py
   python migrar_credenciales.py --apply
   python migrar_credenciales.py
   ```

   La primera ejecución informa cuántas cuentas faltan, sin escribir ni mostrar contraseñas. `--apply` convierte las antiguas, conserva los hashes existentes y revoca sus sesiones. La última inspección debe mostrar cero pendientes. No ejecutar `--apply` antes del SQL: la columna antigua puede ser insuficiente. Si quedan credenciales nulas o datos incompatibles, corregirlos en la copia de prueba antes de continuar.
4. Desplegar la API completa, instalar la nueva app e iniciar sesión. Si una parte falla, mantener la ventana sin escrituras y recuperar el respaldo o corregir la migración; no volver al login antiguo que compara texto plano sobre una base ya convertida.
5. Probar una cuenta por rol y estos recorridos en la base de prueba: cerrar sesión y reutilizar su token → 401; cambiar contraseña → token anterior 401; desactivar y reactivar → token anterior 401; intentar quitar al último gestor → 409; publicar y editar un anuncio de 5.000 caracteres sin cambiar su hora; repetir una asistencia idéntica sin nuevas filas; incrementar inventario desde dos sesiones y comprobar ambos incrementos.

## Contratos actualizados

- Anuncios: descripción obligatoria de hasta **5.000 caracteres** y título de hasta 150. Las fechas representan la hora nominal del evento, sin conversión UTC al editar. El texto se muestra como texto, con saltos de línea; no se interpreta como HTML.
- Creación de anuncio y de sesión de asistencia: la app envía `Idempotency-Key`, una clave aleatoria por intento lógico. Reintentar con la misma clave y contenido reutiliza la respuesta persistida; cambiar el contenido manteniendo la clave devuelve 409. La clave está vinculada al usuario y al tipo de operación. La transacción guarda juntos el recurso y su respuesta. Sin cabecera se conserva la compatibilidad del endpoint, pero no esa protección.
- Inventario: los botones usan `{ "delta": 1 }` o `{ "delta": -1 }`. Una edición absoluta debe enviar `{ "cantidad": 20, "cantidad_anterior": 12 }`; si ya cambió la cantidad, devuelve 409. Se rechazan decimales, booleanos, negativos y desbordamientos. La respuesta devuelve la cantidad resultante.
- Altas desde Gestión: se respeta `activo` 0/1. Registro público: siempre inactivo. Datos y estado se editan en una única solicitud y transacción.
- Consultas: Inicio usa `/traer_anuncios?proximas=1` (máximo 3); Anuncios usa `pagina` y `limite` (máximo 100 por página) y puede priorizar `anuncio`; inventario usa la ruta por proyecto; sesiones acepta `?proyecto=ID`; Gestión obtiene todas las relaciones en `/traer_asignaciones`, sin una solicitud por proyecto.
- Las respuestas privadas usan `Cache-Control: no-store`. Los errores internos de SQL se registran en el servidor y no se devuelven al cliente.

`sesiones_usuario` permite limpiar sesiones vencidas. Los registros de `operaciones_idempotentes` conservan respuestas para reintentos; definir su retención según el tiempo durante el cual se quiere garantizar esa recuperación. Borrarlos permite que un reintento muy antiguo cree una operación nueva.

## Dependencias y alcance de validación

Se fijaron Flask 3.1.3 y Werkzeug 3.1.9. La auditoría de las ocho dependencias Python directas fijadas no encontró vulnerabilidades conocidas el 22/10/2026; se ejecutó sin resolver transitivas. Ejecutar una auditoría completa del entorno instalado en el servidor antes del despliegue.

Las pruebas locales no validan el esquema real, los bloqueos de InnoDB ni las carreras entre procesos MySQL. Esas comprobaciones y los recorridos en teléfonos físicos siguen siendo parte de la aceptación previa al despliegue.
