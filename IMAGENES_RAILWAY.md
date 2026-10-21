# Imágenes de anuncios en Railway

Las rutas de crear y editar anuncios guardan el archivo recibido en `img` con
un nombre UUID. La base de datos conserva ese nombre. La ruta pública
`GET /uploads/<nombre_archivo>` lee desde la misma carpeta.

## Configuración necesaria antes de desplegar

1. En el servicio de la API en Railway, agregar un volumen persistente y
   montarlo en `/data`.
2. Railway proporciona `RAILWAY_VOLUME_MOUNT_PATH`. La aplicación usa
   automáticamente `<montaje>/uploads`, por ejemplo `/data/uploads`.
   Alternativamente configurar `UPLOAD_FOLDER=/data/uploads`; esa variable
   tiene prioridad y debe apuntar dentro del volumen real. Crear solo la
   variable sin montar un volumen no proporciona persistencia.
3. Desplegar el código del backend con `almacenamiento_imagenes.py`.
4. Crear un anuncio con una imagen desde la aplicación y comprobar en otro
   dispositivo `https://<dominio-api>/uploads/<nombre-devuelto-en-img>`.
5. Volver a desplegar la API y comprobar que la misma URL sigue funcionando.

En desarrollo, sin esas variables, se mantiene la carpeta `uploads` junto a
`app.py`. La lectura, creación, reemplazo y eliminación usan siempre
`app.config["UPLOAD_FOLDER"]`.

## Archivos anteriores

Si existen imágenes en la carpeta del despliegue anterior, respaldarlas antes
de cambiar el despliegue y copiarlas al volumen conservando sus nombres.
Agregar el volumen no copia archivos automáticamente. Si los archivos ya se
perdieron, hay que recuperarlos de una copia o volver a subirlos al editar el
anuncio; el nombre almacenado en MySQL no contiene los bytes de la imagen.

## Comprobaciones locales

`python -m unittest -v test_almacenamiento_imagenes`

Estas pruebas comprueban selección de carpeta, creación y conservación de
archivos entre dos directorios de despliegue que comparten un volumen.
La prueba real de subida y lectura requiere la API desplegada y MySQL.

Documentación: https://docs.railway.com/volumes
