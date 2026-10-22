"""Exercise the real Flask routes with a fake database, never production data."""
import importlib
import os
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import MagicMock, patch

from seguridad import emitir_token


class SeguridadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mysql = MagicMock()
        cls.carpeta = tempfile.TemporaryDirectory()
        # mysqlclient is a native production dependency; the unit tests use a double.
        modulo_mysql = types.ModuleType("flask_mysqldb")
        modulo_mysql.MySQL = lambda app: cls.mysql
        with patch.dict(sys.modules, {"flask_mysqldb": modulo_mysql}), patch.dict(os.environ, {"UPLOAD_FOLDER": cls.carpeta.name}):
            cls.modulo = importlib.import_module("app")
        cls.app = cls.modulo.app
        cls.mysql = cls.modulo.mysql
        cls.app.config.update(TESTING=True, SECRET_KEY="clave-exclusiva-para-las-pruebas-no-produccion")

    @classmethod
    def tearDownClass(cls):
        cls.carpeta.cleanup()

    def setUp(self):
        self.mysql.reset_mock()
        self.cursor = MagicMock()
        self.mysql.connection.cursor.return_value = self.cursor
        self.fila = (9, "Ana", "Perez", "ana@example.test", "voluntario", 1, 1)
        self.cursor.fetchone.return_value = self.fila
        self.cliente = self.app.test_client()
        self.token = emitir_token(self.app, 9)
        self.mysql.reset_mock()
        self.headers = {"Authorization": "Bearer " + self.token}

    def test_no_basta_enviar_un_id_o_un_rol_para_autenticarse(self):
        for headers in ({}, {"Authorization": "9", "X-Rol": "administrador"}, {"Authorization": "Bearer inventado"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.cliente.get("/traer_anuncios", headers=headers).status_code, 401)

    def test_una_cuenta_desactivada_pierde_acceso_con_el_mismo_token(self):
        respuesta = self.cliente.get("/sesion_actual", headers=self.headers)
        self.assertEqual(respuesta.status_code, 200)
        self.cursor.fetchone.return_value = (*self.fila[:5], 0, 1)
        for metodo, ruta in (("GET", "/sesion_actual"), ("GET", "/traer_anuncios"), ("POST", "/nueva_sesion")):
            with self.subTest(ruta=ruta):
                respuesta = self.cliente.open(ruta, method=metodo, headers=self.headers, json={})
                self.assertEqual(respuesta.status_code, 403)
                self.assertEqual(respuesta.json["codigo"], "cuenta_deshabilitada")

    def test_cuenta_eliminada_tambien_pierde_acceso(self):
        self.cursor.fetchone.return_value = None
        self.assertEqual(self.cliente.get("/sesion_actual", headers=self.headers).json["codigo"], "cuenta_deshabilitada")

    def test_sesion_devuelve_rol_actual_sin_clave_y_no_se_cachea(self):
        self.cursor.fetchone.return_value = (*self.fila[:4], "referente", 1, 1)
        respuesta = self.cliente.get("/sesion_actual", headers=self.headers)
        self.assertEqual(respuesta.json["usuario"]["perfil"], "referente")
        self.assertNotIn("clave", respuesta.json["usuario"])
        self.assertEqual(respuesta.headers["Cache-Control"], "no-store")

    def test_voluntario_no_puede_mutar_gestion_anuncios_inventario_ni_historial(self):
        rutas = [
            ("GET", "/traer_usuarios_voluntariado"), ("GET", "/traer_destinatarios"),
            ("PUT", "/desactivar_usuario/1"), ("POST", "/nuevo_anuncio"),
            ("PUT", "/actualizar_anuncio/1"), ("DELETE", "/eliminar_anuncio/1"),
            ("POST", "/nuevo_objeto"), ("PUT", "/actualizar_objeto/1"),
            ("DELETE", "/eliminar_objeto/1"), ("POST", "/nuevo_proyecto"),
            ("PUT", "/actualizar_asistencia/1"), ("DELETE", "/eliminar_sesion/1"),
        ]
        for metodo, ruta in rutas:
            with self.subTest(ruta=ruta):
                respuesta = self.cliente.open(ruta, method=metodo, headers=self.headers, json={"perfil": "administrador"})
                self.assertEqual(respuesta.status_code, 403)
                self.assertEqual(respuesta.json["codigo"], "sin_permisos")

    def test_voluntario_puede_leer_y_pasar_asistencia(self):
        permitidos = {
            "listar_anuncios": ("GET", "/traer_anuncios"),
            "traer_proyectos": ("GET", "/traer_proyectos"),
            "traer_inventario": ("GET", "/traer_inventario"),
            "traer_destinatarios_proyecto": ("GET", "/traer_destinatarios_proyecto/1"),
            "traer_sesiones": ("GET", "/traer_sesiones"),
            "nueva_sesion": ("POST", "/nueva_sesion"),
            "guardar_asistencia": ("POST", "/guardar_asistencia"),
        }
        for endpoint, (metodo, ruta) in permitidos.items():
            with self.subTest(ruta=ruta), patch.dict(self.app.view_functions, {endpoint: lambda **kwargs: ("permitido", 200)}):
                self.assertEqual(self.cliente.open(ruta, method=metodo, headers=self.headers).status_code, 200)

    def test_gestores_conservan_operaciones_y_el_rol_se_consulta_de_nuevo(self):
        for rol in ("administrador", "referente", " ADMIN "):
            self.cursor.fetchone.return_value = (*self.fila[:4], rol, 1, 1)
            with self.subTest(rol=rol), patch.dict(self.app.view_functions, {"desactivar_usuario": lambda **kwargs: ("permitido", 200)}):
                self.assertEqual(self.cliente.put("/desactivar_usuario/1", headers=self.headers).status_code, 200)
        self.cursor.fetchone.return_value = self.fila
        self.assertEqual(self.cliente.put("/desactivar_usuario/1", headers=self.headers).status_code, 403)

    def test_no_puede_guardar_en_la_sesion_de_otro_usuario(self):
        self.cursor.fetchone.side_effect = [self.fila, (42, 7, 10)]
        respuesta = self.cliente.post("/guardar_asistencia", headers=self.headers,
            json={"sesiones_idsesion": 42, "asistencias": [{"dni": 123, "presente": 1}]})
        self.assertEqual(respuesta.status_code, 403)
        self.mysql.connection.commit.assert_not_called()

    def test_no_puede_reescribir_una_asistencia_ya_guardada(self):
        self.cursor.fetchone.side_effect = [self.fila, (42, 7, 9)]
        self.cursor.fetchall.return_value = [(123, 0)]
        respuesta = self.cliente.post("/guardar_asistencia", headers=self.headers,
            json={"sesiones_idsesion": 42, "asistencias": [{"dni": 123, "presente": 1}]})
        self.assertEqual(respuesta.status_code, 403)
        self.mysql.connection.commit.assert_not_called()

    def test_el_autor_de_asistencia_es_el_usuario_autenticado(self):
        self.cursor.fetchone.side_effect = [self.fila, (7,), (9,)]
        self.cursor.lastrowid = 42
        respuesta = self.cliente.post("/nueva_sesion", headers=self.headers,
            json={"proyectos_idproyecto": 7, "usuario_idusuario": 999})
        self.assertEqual(respuesta.status_code, 201)
        inserciones = [llamada for llamada in self.cursor.execute.call_args_list if "INSERT INTO" in llamada.args[0]]
        self.assertEqual(inserciones[0].args[1][-1], 9)

    def test_token_expirado_o_alterado_es_rechazado(self):
        with patch("itsdangerous.timed.TimestampSigner.get_timestamp", return_value=int(time.time()) - 13 * 3600):
            vencido = emitir_token(self.app, 9)
        for token in (vencido, self.token + "alterado"):
            with self.subTest(token=token):
                self.assertEqual(self.cliente.get("/sesion_actual", headers={"Authorization": "Bearer " + token}).status_code, 401)

    def test_registro_publico_no_puede_crear_administradores(self):
        respuesta = self.cliente.post("/nuevo_usuario_voluntariado", json={
            "nombre": "Ana", "apellido": "Perez", "mail": "ana@example.test", "clave": "no-real", "perfil": "administrador"
        })
        self.assertEqual(respuesta.status_code, 400)
        self.mysql.connection.commit.assert_not_called()

    def test_login_emite_token_y_no_devuelve_la_clave(self):
        self.cursor.fetchone.return_value = (9, "Ana", "Perez", "ana@example.test", "no-real", "voluntario", 1)
        respuesta = self.cliente.post("/iniciar_sesion", json={"mail": "ana@example.test", "clave": "no-real", "recordarme": True})
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json["token"])
        self.assertNotIn("clave", respuesta.json["usuario"])

    def test_no_hay_fallback_inseguro_si_falta_clave(self):
        with patch.dict(self.app.config, {"SECRET_KEY": None}):
            self.assertEqual(self.cliente.get("/sesion_actual", headers=self.headers).status_code, 503)
            self.assertEqual(self.cliente.post("/iniciar_sesion", json={}).status_code, 503)

    def test_preflight_no_requiere_sesion(self):
        self.assertEqual(self.cliente.options("/guardar_asistencia").status_code, 200)


if __name__ == "__main__":
    unittest.main()
