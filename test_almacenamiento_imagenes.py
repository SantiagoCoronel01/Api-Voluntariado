import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from almacenamiento_imagenes import preparar_carpeta_imagenes


class AlmacenamientoImagenesTest(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.entorno = patch.dict(os.environ, {}, clear=True)
        self.entorno.start()
        self.addCleanup(self.entorno.stop)

    def test_desarrollo_conserva_uploads_junto_a_la_app(self):
        carpeta = preparar_carpeta_imagenes(self.raiz)
        self.assertEqual(Path(carpeta), self.raiz / "uploads")
        self.assertTrue(Path(carpeta).is_dir())

    def test_railway_guarda_en_el_volumen_montado(self):
        os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = str(self.raiz / "volumen")
        carpeta = preparar_carpeta_imagenes(self.raiz / "despliegue")
        self.assertEqual(Path(carpeta), self.raiz / "volumen" / "uploads")
        self.assertTrue(Path(carpeta).is_dir())

    def test_configuracion_explicita_tiene_prioridad(self):
        os.environ["UPLOAD_FOLDER"] = str(self.raiz / "imagenes")
        os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = str(self.raiz / "volumen")
        carpeta = preparar_carpeta_imagenes(self.raiz)
        self.assertEqual(Path(carpeta), self.raiz / "imagenes")

    def test_otro_despliegue_recupera_los_mismos_archivos_del_volumen(self):
        os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = str(self.raiz / "volumen")
        carpeta = preparar_carpeta_imagenes(self.raiz / "despliegue_1")
        imagen = Path(carpeta) / "anuncio.png"
        imagen.write_bytes(b"imagen de prueba")
        otra_carpeta = preparar_carpeta_imagenes(self.raiz / "despliegue_2")
        self.assertEqual((Path(otra_carpeta) / imagen.name).read_bytes(), b"imagen de prueba")

    def test_variables_vacias_usan_el_directorio_local(self):
        os.environ["UPLOAD_FOLDER"] = " "
        os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = " "
        self.assertEqual(Path(preparar_carpeta_imagenes(self.raiz)), self.raiz / "uploads")


if __name__ == "__main__":
    unittest.main()
