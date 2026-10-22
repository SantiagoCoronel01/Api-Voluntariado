from datetime import datetime
from zoneinfo import ZoneInfo
from flask import current_app, jsonify, request
from cuentas import entero


def anuncios(mysql):
    cursor = mysql.connection.cursor()
    try:
        where, valores = [], []
        proximas = request.args.get("proximas") == "1"
        if proximas:
            where.append("fecha_evento >= %s")
            valores.append(datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).replace(tzinfo=None))
        sql = "SELECT idAnuncios,titulo,descripcion,img,fecha_creado,fecha_evento,tipo_evento,usuario_idusuario FROM anuncios"
        if where:
            sql += " WHERE " + " AND ".join(where)
        if proximas:
            sql += " ORDER BY fecha_evento,idAnuncios LIMIT 3"
        else:
            destino = request.args.get("anuncio")
            if destino:
                sql += " ORDER BY (idAnuncios=%s) DESC,fecha_creado DESC,idAnuncios DESC"
                valores.append(entero(destino, 1))
            else:
                sql += " ORDER BY fecha_creado DESC,idAnuncios DESC"
            if request.args.get("pagina"):
                pagina = entero(request.args["pagina"], 1, 1000000)
                limite = entero(request.args.get("limite", 40), 1, 100)
                sql += " LIMIT %s OFFSET %s"
                valores += [limite, (pagina - 1) * limite]
        cursor.execute(sql, tuple(valores))
        campos = ("idAnuncios", "titulo", "descripcion", "img", "fecha_creado", "fecha_evento", "tipo_evento", "usuario")
        return jsonify([dict(zip(campos, fila)) for fila in cursor.fetchall()])
    except ValueError as error:
        return jsonify(resultado=str(error)), 400
    except Exception:
        current_app.logger.exception("Error al consultar anuncios")
        return jsonify(resultado="No se pudieron cargar los anuncios."), 503
    finally:
        cursor.close()


def asignaciones(mysql):
    cursor = mysql.connection.cursor()
    try:
        cursor.execute("SELECT id,destinatarios_dni,proyectos_idproyecto FROM destinatario_proyecto")
        return jsonify([{"id": fila[0], "dni": fila[1], "proyectoId": fila[2]} for fila in cursor.fetchall()])
    except Exception:
        current_app.logger.exception("Error al consultar asignaciones")
        return jsonify(error="No se pudieron consultar las asignaciones."), 503
    finally:
        cursor.close()


def actualizar_objeto(mysql, idobjeto):
    cursor = None
    try:
        datos = request.get_json(silent=True)
        if not isinstance(datos, dict):
            raise ValueError("Enviá un objeto JSON válido.")
        campos, valores = [], []
        if "nombre" in datos:
            nombre = datos["nombre"]
            if not isinstance(nombre, str) or not nombre.strip() or len(nombre.strip()) > 45:
                raise ValueError("El nombre debe tener entre 1 y 45 caracteres.")
            campos.append("nombre=%s")
            valores.append(nombre.strip())
        where = "idRegistro_objetos=%s"
        condicion = [idobjeto]
        if "delta" in datos:
            if "cantidad" in datos:
                raise ValueError("No mezcles cantidad absoluta e incremento.")
            delta = entero(datos["delta"], -1, 1)
            if delta == 0:
                raise ValueError("El incremento debe ser 1 o -1.")
            campos.append("cantidad=cantidad+%s")
            valores.append(delta)
            where += " AND cantidad+%s BETWEEN 0 AND 2147483647"
            condicion.append(delta)
        elif "cantidad" in datos:
            cantidad = entero(datos["cantidad"])
            anterior = entero(datos.get("cantidad_anterior"))
            campos.append("cantidad=%s")
            valores.append(cantidad)
            where += " AND cantidad=%s"
            condicion.append(anterior)
        if not campos:
            raise ValueError("No se enviaron cambios.")
        cursor = mysql.connection.cursor()
        # Lock the object until both the write and its returned quantity are committed.
        cursor.execute("SELECT cantidad FROM inventario WHERE idRegistro_objetos=%s FOR UPDATE", (idobjeto,))
        fila = cursor.fetchone()
        if fila is None:
            mysql.connection.rollback()
            return jsonify(error="Objeto no encontrado"), 404
        if "cantidad" in datos and fila[0] != anterior:
            mysql.connection.rollback()
            return jsonify(error="Otro usuario modificó la cantidad. Recargá el inventario.", codigo="inventario_desactualizado"), 409
        if "delta" in datos and not 0 <= fila[0] + delta <= 2147483647:
            mysql.connection.rollback()
            return jsonify(error="La cantidad está fuera del rango permitido."), 400
        cursor.execute("UPDATE inventario SET " + ",".join(campos) + " WHERE " + where, tuple(valores + condicion))
        cursor.execute("SELECT cantidad FROM inventario WHERE idRegistro_objetos=%s", (idobjeto,))
        cantidad_final = cursor.fetchone()[0]
        mysql.connection.commit()
        return jsonify(resultado="Objeto actualizado correctamente", cantidad=cantidad_final)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except Exception:
        mysql.connection.rollback()
        current_app.logger.exception("Error al actualizar inventario")
        return jsonify(error="No se pudo actualizar el inventario."), 503
    finally:
        if cursor is not None:
            cursor.close()
