from flask import current_app, g, jsonify, request
from cuentas import datos_json, entero
from seguridad import GESTORES


def guardar(mysql):
    cursor = None
    try:
        datos = datos_json()
        sesion_id = entero(datos.get('sesiones_idsesion'), 1)
        lista = datos.get('asistencias')
        if not isinstance(lista, list) or not 1 <= len(lista) <= 10000:
            raise ValueError('Enviá entre 1 y 10000 asistencias.')
        marcas = {}
        for item in lista:
            if not isinstance(item, dict):
                raise ValueError('Cada asistencia debe ser un objeto.')
            dni = entero(item.get('dni'), 1)
            presente = item.get('presente')
            if type(presente) not in (int, bool) or presente not in (0, 1):
                raise ValueError('El estado de asistencia debe ser 0 o 1.')
            if dni in marcas:
                raise ValueError('Hay destinatarios repetidos.')
            marcas[dni] = int(presente)
        cursor = mysql.connection.cursor()
        # Serialize submissions for one session, including requests from two devices.
        cursor.execute('SELECT idsesion,proyectos_idproyecto,usuario_idusuario FROM sesiones_asistencia WHERE idsesion=%s FOR UPDATE', (sesion_id,))
        sesion = cursor.fetchone()
        if sesion is None:
            mysql.connection.rollback()
            return jsonify(error='La sesión no existe'), 404
        if g.rol_actual not in GESTORES and sesion[2] != g.usuario_actual['idusuario']:
            mysql.connection.rollback()
            return jsonify(codigo='sin_permisos', error='No podés modificar la asistencia de otro usuario.'), 403
        cursor.execute('SELECT destinatarios_dni,presente FROM asistencia WHERE sesiones_idsesion=%s', (sesion_id,))
        anteriores = cursor.fetchall()
        if anteriores:
            mysql.connection.rollback()
            if dict(anteriores) == marcas and len(anteriores) == len(marcas):
                return jsonify(resultado='Asistencia ya guardada correctamente', idsesion=sesion_id, cantidad_registrada=len(marcas)), 200
            return jsonify(codigo='asistencia_guardada', error='Esta asistencia ya fue guardada. Solicitá su corrección a un referente.'), 409 if g.rol_actual in GESTORES else 403
        cursor.execute('SELECT destinatarios_dni FROM destinatario_proyecto WHERE proyectos_idproyecto=%s', (sesion[1],))
        permitidos = {fila[0] for fila in cursor.fetchall()}
        if not set(marcas).issubset(permitidos):
            raise ValueError('Hay destinatarios que no pertenecen al proyecto.')
        for dni, presente in marcas.items():
            cursor.execute('INSERT INTO asistencia (sesiones_idsesion,destinatarios_dni,presente) VALUES (%s,%s,%s)', (sesion_id, dni, presente))
        mysql.connection.commit()
        return jsonify(resultado='Asistencia guardada correctamente', idsesion=sesion_id, cantidad_registrada=len(marcas)), 201
    except ValueError as error:
        mysql.connection.rollback()
        return jsonify(error=str(error)), 400
    except Exception:
        mysql.connection.rollback()
        current_app.logger.exception('No se pudo guardar asistencia')
        return jsonify(error='No se pudo guardar la asistencia. Reintentá con los mismos datos.'), 503
    finally:
        if cursor is not None:
            cursor.close()
