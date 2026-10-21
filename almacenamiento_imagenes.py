"""Ubicación compartida por la subida y la lectura de imágenes de anuncios."""
import os


def preparar_carpeta_imagenes(directorio_app):
    carpeta_configurada = os.environ.get("UPLOAD_FOLDER", "").strip()
    volumen = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "").strip()

    if carpeta_configurada:
        carpeta = carpeta_configurada
    elif volumen:
        carpeta = os.path.join(volumen, "uploads")
    else:
        carpeta = os.path.join(directorio_app, "uploads")

    carpeta = os.path.abspath(carpeta)
    os.makedirs(carpeta, exist_ok=True)
    return carpeta
