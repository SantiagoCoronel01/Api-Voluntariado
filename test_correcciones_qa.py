"""Regressions exercise Flask routes and transaction boundaries with a DB double."""
import io
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
from zoneinfo import ZoneInfo
from test_seguridad import SeguridadTest
from credenciales import crear_hash, comprobar_clave, validar_clave
from migrar_credenciales import migrar


class CorreccionesQA(SeguridadTest):
    # Reuse the isolated Flask fixture, without re-running inherited test methods.
    def gestor(self):
        self.fila = (*self.fila[:4], 'administrador', 1, 1)
        self.cursor.fetchone.return_value = self.fila

    def test_login_json_incompleto_o_incorrecto_no_es_500(self):
        for cuerpo in ({}, [], None, {'mail': 'ana@example.test', 'clave': 7}):
            with self.subTest(cuerpo=cuerpo):
                r = self.cliente.post('/iniciar_sesion', json=cuerpo)
                self.assertEqual(r.status_code, 400)

    def test_hash_con_sal_y_verificacion_de_credenciales(self):
        clave = 'PruebaSegura9!'
        primero, segundo = crear_hash(clave), crear_hash(clave)
        self.assertNotEqual(primero, segundo)
        self.assertNotIn(clave, primero)
        self.assertTrue(comprobar_clave(primero, clave))
        self.assertFalse(comprobar_clave(primero, 'Incorrecta9!'))
        for invalida in ('a', 'sinmayuscula9!', 'SinNumeros!', 'SinSimbolo9', 'A1!' * 100):
            self.assertFalse(validar_clave(invalida))

    def test_registro_publico_guarda_hash_y_siempre_inactivo(self):
        self.cursor.fetchone.return_value = None
        r = self.cliente.post('/nuevo_usuario_voluntariado', json={
            'nombre': 'Ana', 'apellido': 'Perez', 'mail': 'ana@example.test',
            'perfil': 'voluntario', 'clave': 'PruebaSegura9!', 'activo': 1})
        self.assertEqual(r.status_code, 201)
        insercion = next(c for c in self.cursor.execute.call_args_list if 'INSERT INTO usuario ' in c.args[0])
        self.assertTrue(comprobar_clave(insercion.args[1][3], 'PruebaSegura9!'))
        self.assertEqual(insercion.args[1][-1], 0)

    def test_gestor_puede_crear_usuario_activo(self):
        self.gestor()
        self.cursor.fetchone.side_effect = [self.fila, None]
        r = self.cliente.post('/nuevo_usuario_voluntariado', headers=self.headers, json={
            'nombre': 'Ana', 'apellido': 'Perez', 'mail': 'otra@example.test',
            'perfil': 'voluntario', 'clave': 'PruebaSegura9!', 'activo': 1})
        self.assertEqual(r.status_code, 201)
        insercion = next(c for c in self.cursor.execute.call_args_list if 'INSERT INTO usuario ' in c.args[0])
        self.assertEqual(insercion.args[1][-1], 1)

    def test_protege_ultimo_gestor_al_desactivar_eliminar_o_cambiar_rol(self):
        self.gestor()
        self.cursor.fetchall.return_value = [(9, 'administrador', 1), (10, 'voluntario', 1)]
        for metodo, ruta, cuerpo in [('PUT', '/desactivar_usuario/9', {}), ('DELETE', '/eliminar_usuario_voluntariado/9', {}),
                                    ('PUT', '/actualizar_usuario_voluntariado/9', {'perfil': 'voluntario'})]:
            with self.subTest(ruta=ruta):
                r = self.cliente.open(ruta, method=metodo, headers=self.headers, json=cuerpo)
                self.assertEqual(r.status_code, 409)
                self.assertEqual(r.json['codigo'], 'ultimo_gestor')
        self.mysql.connection.commit.assert_not_called()

    def test_cambio_clave_y_desactivacion_revocan_en_la_misma_transaccion(self):
        self.gestor()
        self.cursor.fetchall.return_value = [(9, 'administrador', 1), (10, 'voluntario', 1)]
        for ruta, datos in [('/desactivar_usuario/10', {}), ('/actualizar_usuario_voluntariado/10', {'clave': 'NuevaClave9!'})]:
            self.cursor.execute.reset_mock()
            self.assertEqual(self.cliente.put(ruta, headers=self.headers, json=datos).status_code, 200)
            self.assertTrue(any('UPDATE sesiones_usuario SET revocada=1' in c.args[0] for c in self.cursor.execute.call_args_list))

    def test_sesion_revocada_no_revive_con_cuenta_activa(self):
        self.cursor.fetchone.return_value = (*self.fila[:6], 0)
        self.assertEqual(self.cliente.get('/sesion_actual', headers=self.headers).status_code, 401)

    def test_logout_revoca_solo_la_sesion_actual(self):
        self.assertEqual(self.cliente.post('/cerrar_sesion', headers=self.headers).status_code, 200)
        sql = next(c for c in self.cursor.execute.call_args_list if 'UPDATE sesiones_usuario' in c.args[0])
        self.assertIn('token_hash=%s AND idusuario=%s', sql.args[0])
        self.assertEqual(sql.args[1][-1], 9)

    def test_login_migra_clave_antigua_antes_de_emitir_token(self):
        self.cursor.fetchone.return_value = (9, 'Ana', 'Perez', 'ana@example.test', 'antigua', 'voluntario', 1)
        r = self.cliente.post('/iniciar_sesion', json={'mail': 'ana@example.test', 'clave': 'antigua'})
        self.assertEqual(r.status_code, 200)
        actualizacion = next(c for c in self.cursor.execute.call_args_list if 'UPDATE usuario SET clave=' in c.args[0])
        self.assertTrue(comprobar_clave(actualizacion.args[1][0], 'antigua'))

    def test_migracion_modo_inspeccion_no_escribe_y_apply_no_rehashea(self):
        db = MagicMock()
        db.cursor.return_value.fetchall.return_value = [(1, 'legada'), (2, crear_hash('Actual9!'))]
        self.assertEqual(migrar(db), (1, 0))
        db.commit.assert_not_called()
        self.assertFalse(any('UPDATE' in c.args[0] for c in db.cursor.return_value.execute.call_args_list))
        db.cursor.return_value.rowcount = 1
        self.assertEqual(migrar(db, True), (1, 1))

    def anuncio(self, descripcion):
        return {'titulo': 'Jornada', 'descripcion': descripcion, 'fecha_evento': '2026-10-23 17:00:00',
                'tipo_evento': 'Actividades', 'usuario': '999'}

    def test_descripcion_5000_y_autor_autenticado(self):
        self.gestor()
        datos = self.anuncio('ñ' * 5000)
        r = self.cliente.post('/nuevo_anuncio', data=datos, headers=self.headers)
        self.assertEqual(r.status_code, 201)
        insercion = next(c for c in self.cursor.execute.call_args_list if 'INSERT INTO anuncios' in c.args[0])
        self.assertEqual(insercion.args[1][1], datos['descripcion'])
        self.assertEqual(insercion.args[1][-1], 9)
        self.assertEqual(self.cliente.post('/nuevo_anuncio', data=self.anuncio('a' * 5001), headers=self.headers).status_code, 400)
        self.assertEqual(self.cliente.put('/actualizar_anuncio/1', data={'descripcion': 'a' * 5001}, headers=self.headers).status_code, 400)

    def test_cantidades_decimales_bool_y_absolutas_sin_version_rechazadas(self):
        self.gestor()
        for cantidad in (2.9, True, '2.9', -1, 2147483648):
            self.assertEqual(self.cliente.post('/nuevo_objeto', headers=self.headers, json={
                'nombre': 'Pelotas', 'cantidad': cantidad, 'proyectos_idproyecto': 1}).status_code, 400)
        self.assertEqual(self.cliente.put('/actualizar_objeto/1', headers=self.headers, json={'cantidad': 3}).status_code, 400)

    def test_inventario_incrementa_en_sql_y_devuelve_cantidad_real(self):
        self.gestor()
        self.cursor.fetchone.side_effect = [self.fila, (12,), (13,)]
        r = self.cliente.put('/actualizar_objeto/1', headers=self.headers, json={'delta': 1})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json['cantidad'], 13)
        self.assertTrue(any('cantidad=cantidad+%s' in c.args[0] for c in self.cursor.execute.call_args_list))

    def test_inventario_edicion_desactualizada_no_sobrescribe(self):
        self.gestor()
        self.cursor.fetchone.side_effect = [self.fila, (12,)]
        r = self.cliente.put('/actualizar_objeto/1', headers=self.headers, json={'cantidad': 20, 'cantidad_anterior': 10})
        self.assertEqual(r.status_code, 409)
        self.mysql.connection.commit.assert_not_called()

    def test_reintento_asistencia_identica_es_exitoso_sin_insertar(self):
        self.cursor.fetchone.side_effect = [self.fila, (42, 7, 9)]
        self.cursor.fetchall.return_value = [(123, 1)]
        r = self.cliente.post('/guardar_asistencia', headers=self.headers,
            json={'sesiones_idsesion': 42, 'asistencias': [{'dni': 123, 'presente': 1}]})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(any('INSERT INTO asistencia' in c.args[0] for c in self.cursor.execute.call_args_list))

    def test_consulta_home_limitada_en_servidor(self):
        self.cursor.fetchall.return_value = []
        r = self.cliente.get('/traer_anuncios?proximas=1', headers=self.headers)
        self.assertEqual(r.status_code, 200)
        sql = self.cursor.execute.call_args.args[0]
        self.assertIn('fecha_evento >= %s', sql)
        self.assertIn('LIMIT 3', sql)

    def test_anuncios_antiguos_se_consultan_como_informacion_sin_modificar_la_base(self):
        self.cursor.fetchall.return_value = [(15, 'Jornada anterior', 'Se conserva', None,
                                             '2026-10-22', '2026-10-24 17:00:00', 'Medio Ambiente', 9)]
        r = self.cliente.get('/traer_anuncios', headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json[0]['idAnuncios'], 15)
        self.assertEqual(r.json[0]['tipo_evento'], 'Información')
        self.assertFalse(any('UPDATE' in c.args[0] for c in self.cursor.execute.call_args_list))
        self.mysql.connection.commit.assert_not_called()

    def test_anuncios_vigentes_filtran_desde_hoy_antes_de_paginar(self):
        self.cursor.fetchall.return_value = []
        ahora = datetime(2026, 10, 22, 17, 30, tzinfo=ZoneInfo('America/Argentina/Buenos_Aires'))
        with patch('consultas.datetime') as reloj:
            reloj.now.return_value = ahora
            r = self.cliente.get('/traer_anuncios?vigentes=1&pagina=2&limite=40', headers=self.headers)
        self.assertEqual(r.status_code, 200)
        sql, valores = self.cursor.execute.call_args.args
        self.assertIn('WHERE fecha_evento >= %s ORDER BY fecha_evento,idAnuncios LIMIT %s OFFSET %s', sql)
        self.assertEqual(valores, (datetime(2026, 10, 22), 40, 40))
        self.assertNotIn('LIMIT 3', sql)
        reloj.now.assert_called_once_with(ZoneInfo('America/Argentina/Buenos_Aires'))

    def test_enlace_a_anuncio_no_omite_el_filtro_de_dias_anteriores(self):
        self.cursor.fetchall.return_value = []
        r = self.cliente.get('/traer_anuncios?vigentes=1&anuncio=12&pagina=1&limite=40', headers=self.headers)
        self.assertEqual(r.status_code, 200)
        sql, valores = self.cursor.execute.call_args.args
        self.assertIn('WHERE fecha_evento >= %s ORDER BY (idAnuncios=%s) DESC,fecha_evento,idAnuncios', sql)
        self.assertEqual(valores[1:], (12, 40, 0))

    def test_home_conserva_el_filtro_desde_ahora_y_calendario_el_historial(self):
        self.cursor.fetchall.return_value = []
        ahora = datetime(2026, 10, 22, 17, 30, tzinfo=ZoneInfo('America/Argentina/Buenos_Aires'))
        with patch('consultas.datetime') as reloj:
            reloj.now.return_value = ahora
            r = self.cliente.get('/traer_anuncios?proximas=1', headers=self.headers)
        self.assertEqual(r.status_code, 200)
        sql, valores = self.cursor.execute.call_args.args
        self.assertIn('LIMIT 3', sql)
        self.assertEqual(valores, (datetime(2026, 10, 22, 17, 30),))
        r = self.cliente.get('/traer_anuncios', headers=self.headers)
        self.assertEqual(r.status_code, 200)
        sql, valores = self.cursor.execute.call_args.args
        self.assertNotIn('WHERE', sql)
        self.assertEqual(valores, ())

    def test_errores_sql_no_se_filtran_al_cliente(self):
        self.gestor()
        self.cursor.execute.side_effect = [None, RuntimeError('SQL secreto host password tablas')]
        r = self.cliente.post('/nuevo_anuncio', data=self.anuncio('Prueba'), headers=self.headers)
        self.assertGreaterEqual(r.status_code, 400)
        self.assertNotIn('secreto', r.get_data(as_text=True))

    def test_idempotencia_reutiliza_respuesta_y_no_repite_anuncio(self):
        import hashlib, json
        self.gestor()
        datos = self.anuncio('Prueba')
        huella = hashlib.sha256(json.dumps({'json': None, 'form': sorted(datos.items()), 'archivos': []}, sort_keys=True).encode()).hexdigest()
        self.cursor.fetchone.side_effect = [self.fila, (huella, json.dumps({'resultado': 'Anterior', 'img': None}), 201)]
        r = self.cliente.post('/nuevo_anuncio', data=datos, headers={**self.headers, 'Idempotency-Key': 'a' * 32})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json['resultado'], 'Anterior')
        self.assertFalse(any('INSERT INTO anuncios' in c.args[0] for c in self.cursor.execute.call_args_list))


# Inherited cases are already executed by test_seguridad; retain its fixture only.
for nombre in list(SeguridadTest.__dict__):
    if nombre.startswith('test_'):
        setattr(CorreccionesQA, nombre, None)
del SeguridadTest

if __name__ == '__main__':
    unittest.main()
