import hashlib
import json
import re
from functools import wraps
from flask import g, jsonify, make_response, request


def confirmar_transaccion(mysql):
    if not getattr(g, "operacion_idempotente", False):
        mysql.connection.commit()


def idempotente(mysql, operacion):
    def decorar(funcion):
        @wraps(funcion)
        def ejecutar(*args, **kwargs):
            clave = request.headers.get("Idempotency-Key")
            if not clave:
                return funcion(*args, **kwargs)
            if not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", clave):
                return jsonify(error="La clave de operación no es válida."), 400
            partes = {"json": request.get_json(silent=True), "form": sorted(request.form.items()), "archivos": []}
            for nombre, archivo in request.files.items():
                partes["archivos"].append((nombre, hashlib.sha256(archivo.read()).hexdigest()))
                archivo.stream.seek(0)
            huella = hashlib.sha256(json.dumps(partes, sort_keys=True).encode()).hexdigest()
            usuario = g.usuario_actual["idusuario"]
            cursor = mysql.connection.cursor()
            try:
                cursor.execute("INSERT INTO operaciones_idempotentes (idusuario,operacion,clave,payload_hash) VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE clave=clave", (usuario, operacion, clave, huella))
                cursor.execute("SELECT payload_hash,resultado,estado_http FROM operaciones_idempotentes WHERE idusuario=%s AND operacion=%s AND clave=%s FOR UPDATE", (usuario, operacion, clave))
                anterior = cursor.fetchone()
                if anterior[0] != huella:
                    mysql.connection.rollback()
                    return jsonify(error="La clave de operación ya se usó para otros datos."), 409
                if anterior[1] is not None:
                    mysql.connection.rollback()
                    return jsonify(json.loads(anterior[1])), anterior[2]
                g.operacion_idempotente = True
                respuesta = make_response(funcion(*args, **kwargs))
                if respuesta.status_code >= 400:
                    mysql.connection.rollback()
                    return respuesta
                cursor.execute("UPDATE operaciones_idempotentes SET resultado=%s,estado_http=%s WHERE idusuario=%s AND operacion=%s AND clave=%s",
                               (json.dumps(respuesta.get_json()), respuesta.status_code, usuario, operacion, clave))
                mysql.connection.commit()
                return respuesta
            except Exception:
                mysql.connection.rollback()
                raise
            finally:
                g.operacion_idempotente = False
                cursor.close()
        return ejecutar
    return decorar
