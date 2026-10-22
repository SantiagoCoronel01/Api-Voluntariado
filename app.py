from flask import Flask, request, jsonify, g
from flask.helpers import make_response
from flask_mysqldb import MySQL
from flask_cors import CORS, cross_origin
from flask import send_from_directory

from datetime import datetime
from zoneinfo import ZoneInfo

from werkzeug.utils import secure_filename
from uuid import uuid4

import os
import asistencias
import cuentas
import consultas
from anuncios_validacion import validar_anuncio
from idempotencia import idempotente, confirmar_transaccion
from almacenamiento_imagenes import preparar_carpeta_imagenes
from seguridad import emitir_token, instalar_seguridad, GESTORES, ROLES, normalizar_rol
# para subir archivos

#from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")

app.config["MYSQL_HOST"] = os.environ.get("DB_HOST")
app.config["MYSQL_USER"] = os.environ.get("DB_USER")
app.config["MYSQL_PASSWORD"] = os.environ.get("DB_PASSWORD")
app.config["MYSQL_DB"] = os.environ.get("DB_NAME")
app.config["MYSQL_CHARSET"] = "utf8mb4"

mysql = MySQL(app)
instalar_seguridad(app, mysql)
# =========================================================
# IMAGENES DE ANUNCIOS
# =========================================================

# Railway monta el volumen en RAILWAY_VOLUME_MOUNT_PATH.
# UPLOAD_FOLDER permite elegir explícitamente una carpeta persistente.
app.config["UPLOAD_FOLDER"] = preparar_carpeta_imagenes(
    os.path.dirname(os.path.abspath(__file__))
)

app.config["MAX_CONTENT_LENGTH"] = (
    5 * 1024 * 1024
)


EXTENSIONES_PERMITIDAS = {
    "png",
    "jpg",
    "jpeg",
    "webp"
}


def extension_permitida(
    nombre_archivo
):

    return (
        "." in nombre_archivo
        and
        nombre_archivo
        .rsplit(".", 1)[1]
        .lower()
        in EXTENSIONES_PERMITIDAS
    )
# =========================================================
# CORS
# =========================================================

CORS(
    app,
    resources={
        r"/*": {
            "origins": "*",
            "methods": [
                "GET",
                "POST",
                "PUT",
                "DELETE",
                "OPTIONS"
            ],
            "allow_headers": [
                "Content-Type",
                "Authorization", "Idempotency-Key"
            ]
        }
    }
)

#LINEAS DE PRUEBA
###CREAR USUARIO
@app.route("/nuevo_usuario", methods=["POST"])
@cross_origin()
def insertar_usuario():
    nombre = request.json["nombre"]
    apellido = request.json["apellido"]
    provincia = request.json["provincia"]

    cursor = mysql.connection.cursor()

    sql = "INSERT INTO Usuarios(nombre, apellido, provincia) values(%s, %s, %s);"
    cursor.execute(sql, (nombre, apellido, provincia))

    mysql.connection.commit()

    cursor.close()
    response = make_response()

    response = jsonify({"resultado":"Agregado nuevo usuario"})
    return response


###TRAER USUARIOS
@app.route("/traer_usuarios", methods=["GET"])
@cross_origin()
def listar_jugadores():
    #consulta SQL
    sql = "SELECT idUsuarios, nombre, apellido, provincia FROM Usuarios"

    #crear el cursor
    cursor = mysql.connection.cursor()
    cursor.execute(sql)

    resultado = cursor.fetchall()

    #cerrar la conexión
    cursor.close()
    response = make_response()

    if resultado == None:
        response = jsonify({"mensaje":None})
        return response
    else:
        usuarios = []

        for i in resultado:

            p = {
                "id":i[0],
                "nombre":i[1],
                "apellido":i[2],
                "provincia":i[3]
            }

            usuarios.append(p)

        return jsonify(usuarios)


###ELIMINAR USUARIO
@cross_origin
@app.route("/eliminar_usuario_prueba/<id>", methods=["DELETE"])
def eliminar_usuario(id):

    sql = "DELETE FROM Usuarios WHERE idUsuarios=%s"

    #crear el cursor
    cursor = mysql.connection.cursor()
    cursor.execute(sql, (id,))

    mysql.connection.commit()

    #cerrar la conexión
    cursor.close()
    response = make_response()

    response = jsonify({"resultado":"Usuario eliminado"})
    return response


###ACTUALIZAR USUARIO
@cross_origin
@app.route("/actualizar_usuario_prueba/<id>", methods=["PUT"])
def actualizar_usuario(id):

    nombre = request.json["nom"]

    sql = "UPDATE Usuarios SET nombre=%s WHERE idUsuarios=%s"

    #crear el cursor
    cursor = mysql.connection.cursor()
    cursor.execute(sql, (nombre, id))

    mysql.connection.commit()

    #cerrar la conexión
    cursor.close()
    response = make_response()

    response = jsonify({"resultado":"Usuario no activo"})
    return response


#####################################################################
#######################LINEAS VOLUNTARIADO###########################
####################### GESTION USUARIOS ##############################

@app.route("/nuevo_usuario_voluntariado", methods=["POST"])
@cross_origin()
def insertar_usuario_voluntariado():

    return cuentas.registrar(mysql)


###TRAER USUARIOS
@app.route("/traer_usuarios_voluntariado", methods=["GET"])
@cross_origin()
def listar_usuarios_voluntariado():

    sql = """
    SELECT idusuario, nombre, apellido, mail, clave, perfil, activo
    FROM usuario
    """

    cursor = mysql.connection.cursor()
    cursor.execute(sql)

    resultado = cursor.fetchall()
    cursor.close()

    if resultado is None:
        return jsonify({"mensaje": None})

    usuarios = []

    for i in resultado:

        usuarios.append({
            "idusuario": i[0],
            "nombre": i[1],
            "apellido": i[2],
            "mail": i[3],
            "perfil": i[5],
            "activo": i[6]
        })

    return jsonify(usuarios)


###ELIMINAR USUARIO
@app.route("/desactivar_usuario/<id>", methods=["PUT"])
@cross_origin()
def desactivar_usuario(id):

    return cuentas.modificar(mysql, id, estado=0)

### ELIMINAR USUARIO VOLUNTARIADO
@app.route("/eliminar_usuario_voluntariado/<int:id>", methods=["DELETE"])
@cross_origin()
def eliminar_usuario_voluntariado(id):

    return cuentas.modificar(mysql, id, eliminar=True)

### ACTIVAR USUARIO
@app.route("/activar_usuario/<id>", methods=["PUT"])
@cross_origin()
def activar_usuario(id):

    return cuentas.modificar(mysql, id, estado=1)


### ACTUALIZAR USUARIO
@app.route("/actualizar_usuario_voluntariado/<id>", methods=["PUT"])
@cross_origin()
def actualizar_usuario_voluntariado(id):

    return cuentas.modificar(mysql, id)


############################ INICIAR SESIÓN ############################

@app.route("/iniciar_sesion", methods=["POST"])
@cross_origin()
def iniciar_sesion():

    return cuentas.iniciar(mysql)


####################### GESTION ANUNCIOS ##############################

# =========================================================
# TRAER IMAGEN
# =========================================================

@app.route(
    "/uploads/<path:nombre_archivo>",
    methods=["GET"]
)
@cross_origin()
def obtener_imagen(
    nombre_archivo
):

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        nombre_archivo
    )


# =========================================================
# CREAR ANUNCIO
# =========================================================

@app.route(
    "/nuevo_anuncio",
    methods=["POST"]
)
@cross_origin()
def insertar_anuncio():

    try:
        validar_anuncio(request.form)
    except ValueError as error:
        return jsonify(resultado=str(error)), 400

    titulo = request.form.get(
        "titulo",
        ""
    ).strip()

    descripcion = request.form.get(
        "descripcion",
        ""
    ).strip()

    fecha_evento = request.form.get(
        "fecha_evento",
        ""
    ).strip()

    tipo_evento = request.form.get(
        "tipo_evento",
        ""
    ).strip()

    usuario = g.usuario_actual["idusuario"]

    imagen = request.files.get(
        "img"
    )


    # =========================
    # VALIDACIÓN
    # =========================

    if (
        titulo == ""
        or descripcion == ""
        or fecha_evento == ""
        or tipo_evento == ""
        or usuario is None
    ):

        return jsonify({
            "resultado":
                "Todos los campos son obligatorios"
        }), 400


    nombre_archivo = None
    ruta_imagen = None

    if imagen is not None and imagen.filename:
        if not extension_permitida(
            imagen.filename
        ):

            return jsonify({
                "resultado":
                    "Formato de imagen no permitido"
            }), 400


        # =========================
        # GUARDAR IMAGEN
        # =========================

        nombre_original = (
            secure_filename(
                imagen.filename
            )
        )


        extension = (
            nombre_original
            .rsplit(".", 1)[1]
            .lower()
        )


        nombre_archivo = (
            f"{uuid4().hex}.{extension}"
        )


        ruta_imagen = os.path.join(
            app.config["UPLOAD_FOLDER"],
            nombre_archivo
        )


        imagen.save(
            ruta_imagen
        )


    # =========================
    # MYSQL
    # =========================

    cursor = mysql.connection.cursor()


    try:

        sql = """
        INSERT INTO anuncios
        (
            titulo,
            descripcion,
            img,
            fecha_evento,
            tipo_evento,
            usuario_idusuario
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """


        cursor.execute(
            sql,
            (
                titulo,
                descripcion,
                nombre_archivo,
                fecha_evento,
                tipo_evento,
                usuario
            )
        )


        confirmar_transaccion(mysql)


        return jsonify({

            "resultado":
                "Anuncio agregado correctamente",

            "img":
                nombre_archivo

        }), 201


    except Exception as e:

        mysql.connection.rollback()


        if ruta_imagen is not None and os.path.exists(
            ruta_imagen
        ):

            os.remove(
                ruta_imagen
            )


        return jsonify({

            "resultado":
                "No se pudo crear el anuncio",

            "error":
                "No se pudo completar la operación. Intentá nuevamente."

        }), 400


    finally:

        cursor.close()


# =========================================================
# TRAER ANUNCIOS
# =========================================================

@app.route(
    "/traer_anuncios",
    methods=["GET"]
)
@cross_origin()
def listar_anuncios():

    return consultas.anuncios(mysql)


# =========================================================
# ACTUALIZAR ANUNCIO
# =========================================================

@app.route(
    "/actualizar_anuncio/<int:id>",
    methods=["PUT"]
)
@cross_origin()
def actualizar_anuncio(id):

    try:
        validar_anuncio(request.form, parcial=True)
    except ValueError as error:
        return jsonify(resultado=str(error)), 400

    cursor = mysql.connection.cursor()

    nueva_ruta = None

    nuevo_nombre = None

    imagen_anterior = None


    try:

        # =========================
        # COMPROBAR ANUNCIO
        # =========================

        cursor.execute(
            """
            SELECT img
            FROM anuncios
            WHERE idAnuncios=%s
            """,
            (id,)
        )


        anuncio_actual = (
            cursor.fetchone()
        )


        if anuncio_actual is None:

            return jsonify({
                "resultado":
                    "Anuncio no encontrado"
            }), 404


        imagen_anterior = (
            anuncio_actual[0]
        )


        campos = []

        valores = []


        # =========================
        # DATOS DE TEXTO
        # =========================

        titulo = request.form.get(
            "titulo"
        )

        descripcion = request.form.get(
            "descripcion"
        )

        fecha_evento = request.form.get(
            "fecha_evento"
        )

        tipo_evento = request.form.get(
            "tipo_evento"
        )


        if titulo is not None:

            campos.append(
                "titulo=%s"
            )

            valores.append(
                titulo
            )


        if descripcion is not None:

            campos.append(
                "descripcion=%s"
            )

            valores.append(
                descripcion
            )


        if fecha_evento is not None:

            campos.append(
                "fecha_evento=%s"
            )

            valores.append(
                fecha_evento
            )


        if tipo_evento is not None:

            campos.append(
                "tipo_evento=%s"
            )

            valores.append(
                tipo_evento
            )


        # =========================
        # NUEVA IMAGEN
        # =========================

        imagen = request.files.get(
            "img"
        )


        if (
            imagen is not None
            and imagen.filename != ""
        ):

            if not extension_permitida(
                imagen.filename
            ):

                return jsonify({
                    "resultado":
                        "Formato de imagen no permitido"
                }), 400


            nombre_original = (
                secure_filename(
                    imagen.filename
                )
            )


            extension = (
                nombre_original
                .rsplit(".", 1)[1]
                .lower()
            )


            nuevo_nombre = (
                f"{uuid4().hex}.{extension}"
            )


            nueva_ruta = os.path.join(
                app.config[
                    "UPLOAD_FOLDER"
                ],
                nuevo_nombre
            )


            imagen.save(
                nueva_ruta
            )


            campos.append(
                "img=%s"
            )


            valores.append(
                nuevo_nombre
            )


        # =========================
        # SIN CAMBIOS
        # =========================

        if len(campos) == 0:

            return jsonify({
                "resultado":
                    "No se enviaron datos para actualizar"
            }), 400


        # =========================
        # UPDATE
        # =========================

        sql = f"""
        UPDATE anuncios
        SET {', '.join(campos)}
        WHERE idAnuncios=%s
        """


        valores.append(
            id
        )


        cursor.execute(
            sql,
            tuple(valores)
        )


        mysql.connection.commit()


        # =========================
        # BORRAR IMAGEN VIEJA
        # =========================

        if (
            nuevo_nombre
            and imagen_anterior
            and nuevo_nombre
            != imagen_anterior
        ):

            ruta_anterior = (
                os.path.join(
                    app.config[
                        "UPLOAD_FOLDER"
                    ],
                    imagen_anterior
                )
            )


            if os.path.exists(
                ruta_anterior
            ):

                os.remove(
                    ruta_anterior
                )


        return jsonify({
            "resultado":
                "Anuncio actualizado correctamente"
        })


    except Exception as e:

        mysql.connection.rollback()

        if (
            nueva_ruta
            and os.path.exists(
                nueva_ruta
            )
        ):

            os.remove(
                nueva_ruta
            )


        return jsonify({

            "resultado":
                "No se pudo actualizar el anuncio",

            "error":
                "No se pudo completar la operación. Intentá nuevamente."

        }), 400


    finally:

        cursor.close()


# =========================================================
# ELIMINAR ANUNCIO
# =========================================================

@app.route(
    "/eliminar_anuncio/<int:id>",
    methods=["DELETE"]
)
@cross_origin()
def eliminar_anuncio(id):

    cursor = mysql.connection.cursor()


    try:

        cursor.execute(
            """
            SELECT img
            FROM anuncios
            WHERE idAnuncios=%s
            """,
            (id,)
        )


        resultado = (
            cursor.fetchone()
        )


        if resultado is None:

            return jsonify({
                "resultado":
                    "Anuncio no encontrado"
            }), 404


        nombre_imagen = (
            resultado[0]
        )


        cursor.execute(
            """
            DELETE FROM anuncios
            WHERE idAnuncios=%s
            """,
            (id,)
        )


        mysql.connection.commit()


        if nombre_imagen:

            ruta_imagen = os.path.join(
                app.config[
                    "UPLOAD_FOLDER"
                ],
                nombre_imagen
            )


            if os.path.exists(
                ruta_imagen
            ):

                os.remove(
                    ruta_imagen
                )


        return jsonify({
            "resultado":
                "Anuncio eliminado correctamente"
        })


    except Exception as e:

        mysql.connection.rollback()


        return jsonify({

            "resultado":
                "No se pudo eliminar el anuncio",

            "error":
                "No se pudo completar la operación. Intentá nuevamente."

        }), 400


    finally:

        cursor.close()



####################### GESTION INVENTARIO ##############################

# =========================================================
# AGREGAR OBJETO Y ASIGNARLO A UN PROYECTO
# =========================================================


@app.route("/nuevo_objeto", methods=["POST"])
@cross_origin()
def anadir_objeto():
    datos = request.get_json(silent=True) or {}

    nombre = datos.get("nombre", "")
    if not isinstance(nombre, str) or not 1 <= len(nombre.strip()) <= 45:
        return jsonify(error="El nombre debe tener entre 1 y 45 caracteres."), 400
    nombre = nombre.strip()
    cantidad = datos.get("cantidad")
    id_proyecto = datos.get("proyectos_idproyecto")

    if not nombre or cantidad is None or id_proyecto is None:
        return jsonify({
            "error": "Nombre, cantidad y proyecto son obligatorios"
        }), 400

    try:
        cantidad = cuentas.entero(cantidad)
        id_proyecto = cuentas.entero(id_proyecto, 1)

        if cantidad < 0:
            raise ValueError()

    except (ValueError, TypeError):
        return jsonify({
            "error": "La cantidad o el ID del proyecto no son válidos"
        }), 400

    cursor = mysql.connection.cursor()

    try:
        cursor.execute(
            "SELECT idproyecto FROM proyectos WHERE idproyecto = %s",
            (id_proyecto,)
        )

        if cursor.fetchone() is None:
            return jsonify({
                "error": "El proyecto seleccionado no existe"
            }), 400

        # Guardar el objeto y su proyecto.
        cursor.execute(
            """
            INSERT INTO inventario (nombre, cantidad, idProyecto)
            VALUES (%s, %s, %s)
            """,
            (nombre, cantidad, id_proyecto)
        )

        id_objeto = cursor.lastrowid

        # Vincularlo usando el nombre correcto de la columna.
        cursor.execute(
            """
            INSERT INTO inventario_proyecto
                (inventario_id, proyectos_idproyecto)
            VALUES (%s, %s)
            """,
            (id_objeto, id_proyecto)
        )

        mysql.connection.commit()

        return jsonify({
            "resultado": "Objeto agregado correctamente",
            "idRegistro_objetos": id_objeto,
            "proyectos_idproyecto": id_proyecto
        }), 201

    except Exception as e:
        mysql.connection.rollback()
        app.logger.exception("Error al guardar objeto")

        return jsonify({
            "error": "No se pudo completar la operación. Intentá nuevamente."
        }), 500

    finally:
        cursor.close()


# =========================================================
# TRAER INVENTARIO DE UN PROYECTO
# =========================================================



@app.route("/traer_inventario_proyecto/<int:idproyecto>", methods=["GET"])
@cross_origin()
def traer_inventario_proyecto(idproyecto):
    cursor = mysql.connection.cursor()

    try:
        consulta = """
            SELECT
                i.idRegistro_objetos,
                i.nombre,
                i.cantidad,
                COALESCE(
                    ip.proyectos_idproyecto,
                    i.idProyecto
                ) AS id_proyecto
            FROM inventario AS i
            LEFT JOIN inventario_proyecto AS ip
                ON i.idRegistro_objetos = ip.inventario_id
            WHERE
                ip.proyectos_idproyecto = %s
                OR (
                    ip.id IS NULL
                    AND i.idProyecto = %s
                )
            ORDER BY i.nombre
        """

        cursor.execute(consulta, (idproyecto, idproyecto))
        filas = cursor.fetchall()

        columnas = [columna[0] for columna in cursor.description]
        resultado = [
            dict(zip(columnas, fila))
            for fila in filas
        ]

        return jsonify(resultado), 200

    except Exception:
        app.logger.exception(
            "Error al cargar inventario del proyecto %s",
            idproyecto
        )

        return jsonify({
            "error": "No se pudo cargar el inventario"
        }), 500

    finally:
        cursor.close()

# =========================================================
# TRAER TODO EL INVENTARIO CON SUS PROYECTOS
# =========================================================



@app.route("/traer_inventario", methods=["GET"])
@cross_origin()
def traer_inventario():
    cursor = None

    try:
        cursor = mysql.connection.cursor()

        consulta = """
            SELECT
                i.idRegistro_objetos,
                i.nombre,
                i.cantidad,
                COALESCE(
                    ip.proyectos_idproyecto,
                    i.idProyecto
                ) AS id_proyecto,
                p.nombre AS proyecto
            FROM inventario AS i
            LEFT JOIN inventario_proyecto AS ip
                ON ip.inventario_id = i.idRegistro_objetos
            LEFT JOIN proyectos AS p
                ON p.idproyecto = COALESCE(
                    ip.proyectos_idproyecto,
                    i.idProyecto
                )
            ORDER BY i.nombre
        """

        cursor.execute(consulta)
        filas = cursor.fetchall()

        resultado = [
            {
                "idRegistro_objetos": fila[0],
                "nombre": fila[1],
                "cantidad": fila[2],
                "id_proyecto": fila[3],
                "proyecto": fila[4]
            }
            for fila in filas
        ]

        return jsonify(resultado), 200

    except Exception as e:
        app.logger.exception(
            "Error al consultar todo el inventario"
        )

        return jsonify({
            "error": "No se pudo completar la operación. Intentá nuevamente."
        }), 500

    finally:
        if cursor is not None:
            cursor.close()
############################ ACTUALIZAR OBJETO ############################

@app.route("/actualizar_objeto/<int:id>", methods=["PUT"])
@cross_origin()
def actualizar_objeto(id):

    return consultas.actualizar_objeto(mysql, id)


############################ ELIMINAR OBJETO ############################

@app.route("/eliminar_objeto/<int:id>", methods=["DELETE"])
@cross_origin()
def eliminar_objeto(id):

    cursor = mysql.connection.cursor()

    try:
        # Primero eliminar las relaciones del objeto.
        cursor.execute(
            """
            DELETE FROM inventario_proyecto
            WHERE inventario_id = %s
            """,
            (id,)
        )

        # Después eliminar el objeto.
        cursor.execute(
            """
            DELETE FROM inventario
            WHERE idRegistro_objetos = %s
            """,
            (id,)
        )

        if cursor.rowcount == 0:
            mysql.connection.rollback()

            return jsonify({
                "error": "Objeto no encontrado"
            }), 404

        mysql.connection.commit()

        return jsonify({
            "resultado": "Objeto eliminado correctamente"
        }), 200

    except Exception as e:
        mysql.connection.rollback()

        return jsonify({
            "error": "No se pudo completar la operación. Intentá nuevamente."
        }), 400

    finally:
        cursor.close()


####################### GESTION DESTINATARIOS##############################

############################ REGISTRAR DESTINATARIO ############################


@app.route("/nuevo_destinatario", methods=["POST"])
@cross_origin()
def registrar_destinatario():
    datos = request.get_json(silent=True) or {}
    if not isinstance(datos, dict):
        return jsonify({"resultado": "Los datos enviados no son validos"}), 400
    campos_texto = (
        "nombres", "apellidos", "fecha_nacimiento", "domicilio", "escuela_anio",
        "adulto_responsable_uno", "adulto_responsable_dos",
        "personas_autorizadas_retiro", "quien_vive", "condicion_salud"
    )
    valores_texto = {campo: str(datos.get(campo) or "").strip() for campo in campos_texto}
    if not all(valores_texto.values()):
        return jsonify({"resultado": "Completa todos los campos obligatorios del destinatario"}), 400

    proyecto_id = datos.get("proyectos_idproyecto", datos.get("proyecto"))
    try:
        dni = int(datos.get("dni"))
        retirar_solo = int(datos.get("retirar_solo"))
        if proyecto_id is not None:
            proyecto_id = int(proyecto_id)
        if dni <= 0 or retirar_solo not in (0, 1) or (proyecto_id is not None and proyecto_id <= 0):
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({"resultado": "Revisa el DNI, el proyecto y la autorizacion de retiro"}), 400

    email = str(datos.get("email") or "").strip()
    cursor = mysql.connection.cursor()
    try:
        if proyecto_id is not None:
            cursor.execute("SELECT idproyecto FROM proyectos WHERE idproyecto = %s", (proyecto_id,))
            if cursor.fetchone() is None:
                return jsonify({"resultado": "El proyecto seleccionado no existe"}), 404

        cursor.execute("SELECT dni FROM destinatarios WHERE dni = %s", (dni,))
        if cursor.fetchone() is not None:
            return jsonify({"resultado": "Ya existe un destinatario con ese DNI"}), 409

        cursor.execute("""
            INSERT INTO destinatarios (
                nombres, apellidos, dni, fecha_nacimiento, domicilio, escuela_anio,
                retirar_solo, adulto_responsable_uno, adulto_responsable_dos,
                personas_autorizadas_retiro, quien_vive, condicion_salud, email
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            valores_texto["nombres"], valores_texto["apellidos"], dni,
            valores_texto["fecha_nacimiento"], valores_texto["domicilio"],
            valores_texto["escuela_anio"], retirar_solo,
            valores_texto["adulto_responsable_uno"], valores_texto["adulto_responsable_dos"],
            valores_texto["personas_autorizadas_retiro"], valores_texto["quien_vive"],
            valores_texto["condicion_salud"], email
        ))
        if proyecto_id is not None:
            cursor.execute("""
                INSERT INTO destinatario_proyecto (destinatarios_dni, proyectos_idproyecto)
                VALUES (%s, %s)
            """, (dni, proyecto_id))
        mysql.connection.commit()
        return jsonify({"resultado": "Destinatario registrado", "dni": dni}), 201
    except Exception as e:
        mysql.connection.rollback()
        app.logger.exception("Error al crear destinatario")
        return jsonify({"resultado": "No se pudo crear el destinatario", "error": "No se pudo completar la operación. Intentá nuevamente."}), 500
    finally:
        cursor.close()


############################ TRAER DESTINATARIOS ############################

@app.route("/traer_destinatarios", methods=["GET"])
@cross_origin()
def traer_destinatarios():

    sql = """
    SELECT
        nombres,
        apellidos,
        dni,
        fecha_nacimiento,
        domicilio,
        escuela_anio,
        retirar_solo,
        adulto_responsable_uno,
        adulto_responsable_dos,
        personas_autorizadas_retiro,
        quien_vive,
        condicion_salud,
        email
    FROM destinatarios
    """

    cursor = mysql.connection.cursor()
    cursor.execute(sql)

    resultado = cursor.fetchall()
    cursor.close()

    destinatarios = []

    for i in resultado:

        destinatarios.append({
            "nombres": i[0],
            "apellidos": i[1],
            "dni": i[2],
            "fecha_nacimiento": i[3],
            "domicilio": i[4],
            "escuela_anio": i[5],
            "retirar_solo": i[6],
            "adulto_responsable_uno": i[7],
            "adulto_responsable_dos": i[8],
            "personas_autorizadas_retiro": i[9],
            "quien_vive": i[10],
            "condicion_salud": i[11],
            "email": i[12]
        })

    return jsonify(destinatarios)



############################ ACTUALIZAR DESTINATARIO ############################

@app.route("/actualizar_destinatario/<int:dni>", methods=["PUT"])
@cross_origin()
def actualizar_destinatario(dni):

    datos = request.get_json(silent=True) or {}

    if not isinstance(datos, dict):
        return jsonify({
            "resultado": "Los datos enviados no son válidos"
        }), 400

    campos_permitidos = {
        "nombres",
        "apellidos",
        "fecha_nacimiento",
        "domicilio",
        "escuela_anio",
        "retirar_solo",
        "adulto_responsable_uno",
        "adulto_responsable_dos",
        "personas_autorizadas_retiro",
        "quien_vive",
        "condicion_salud",
        "email"
    }

    campos = []
    valores = []

    for campo in campos_permitidos:
        if campo in datos:
            campos.append(f"`{campo}` = %s")
            valores.append(datos[campo])

    if not campos:
        return jsonify({
            "resultado": "No se enviaron datos para actualizar"
        }), 400

    cursor = mysql.connection.cursor()

    try:
        cursor.execute(
            "SELECT dni FROM destinatarios WHERE dni = %s",
            (dni,)
        )

        if cursor.fetchone() is None:
            return jsonify({
                "resultado": "Destinatario no encontrado",
                "dni": dni
            }), 404

        sql = (
            "UPDATE destinatarios SET "
            + ", ".join(campos)
            + " WHERE dni = %s"
        )

        valores.append(dni)

        cursor.execute(sql, tuple(valores))
        mysql.connection.commit()

        return jsonify({
            "resultado": "Destinatario actualizado correctamente",
            "dni": dni
        }), 200

    except Exception as e:
        mysql.connection.rollback()

        app.logger.exception(
            "Error al actualizar destinatario con DNI %s",
            dni
        )

        return jsonify({
            "resultado": "No se pudo actualizar el destinatario",
            "error": "No se pudo completar la operación. Intentá nuevamente."
        }), 500

    finally:
        cursor.close()


############################ ELIMINAR DESTINATARIO ############################

@app.route("/eliminar_destinatario/<int:dni>", methods=["DELETE"])
@cross_origin()
def eliminar_destinatario(dni):

    sql = "DELETE FROM destinatarios WHERE dni=%s"

    cursor = mysql.connection.cursor()
    cursor.execute(sql, (dni,))

    mysql.connection.commit()
    cursor.close()

    return jsonify({
        "resultado": "Destinatario eliminado correctamente"
    })


####################### GESTION PROYECTOS ##############################

####################### AÑADIR PROYECTO ##############################

@app.route("/nuevo_proyecto", methods=["POST"])
@cross_origin()
def agregar_proyecto():
    datos = request.get_json(silent=True) or {}

    nombre = datos.get("nombre", "").strip()
    descripcion = datos.get("descripcion", "").strip()
    estado = datos.get("estado", "Activo").strip()

    if not nombre:
        return jsonify({
            "resultado": "El nombre del proyecto es obligatorio"
        }), 400

    if estado not in ("Activo", "Inactivo"):
        return jsonify({
            "resultado": "El estado debe ser Activo o Inactivo"
        }), 400

    cursor = mysql.connection.cursor()

    try:
        sql = """
            INSERT INTO proyectos (nombre, descripcion, estado)
            VALUES (%s, %s, %s)
        """

        cursor.execute(sql, (nombre, descripcion, estado))
        mysql.connection.commit()

        nuevo_id = cursor.lastrowid

        return jsonify({
            "resultado": "Proyecto agregado correctamente",
            "idproyecto": nuevo_id
        }), 201

    except Exception as e:
        mysql.connection.rollback()
        print("Error al agregar proyecto:", e)

        return jsonify({
            "resultado": "No se pudo agregar el proyecto",
            "error": "No se pudo completar la operación. Intentá nuevamente."
        }), 400

    finally:
        cursor.close()


####################### TRAER PROYECTOS ##############################

@app.route("/traer_proyectos", methods=["GET"])
@cross_origin()
def traer_proyectos():
    cursor = mysql.connection.cursor()

    try:
        sql = """
            SELECT idproyecto, nombre, descripcion, estado
            FROM proyectos
            ORDER BY idproyecto DESC
        """

        cursor.execute(sql)
        resultado = cursor.fetchall()

        proyectos = []

        for fila in resultado:
            proyectos.append({
                "idproyecto": fila[0],
                "nombre": fila[1],
                "descripcion": fila[2] or "",
                "estado": fila[3]
            })

        return jsonify(proyectos), 200

    except Exception as e:
        print("Error al traer proyectos:", e)

        return jsonify({
            "resultado": "No se pudieron traer los proyectos",
            "error": "No se pudo completar la operación. Intentá nuevamente."
        }), 500

    finally:
        cursor.close()


####################### ACTUALIZAR PROYECTO ##############################

@app.route("/actualizar_proyecto/<int:id>", methods=["PUT"])
@cross_origin()
def actualizar_proyecto(id):
    datos = request.get_json(silent=True) or {}

    nombre = datos.get("nombre")
    descripcion = datos.get("descripcion")
    estado = datos.get("estado")

    campos = []
    valores = []

    if nombre is not None:
        nombre = nombre.strip()

        if not nombre:
            return jsonify({
                "resultado": "El nombre del proyecto es obligatorio"
            }), 400

        campos.append("nombre=%s")
        valores.append(nombre)

    if descripcion is not None:
        campos.append("descripcion=%s")
        valores.append(descripcion.strip())

    if estado is not None:
        estado = estado.strip()

        if estado not in ("Activo", "Inactivo"):
            return jsonify({
                "resultado": "El estado debe ser Activo o Inactivo"
            }), 400

        campos.append("estado=%s")
        valores.append(estado)

    if not campos:
        return jsonify({
            "resultado": "No se enviaron datos para actualizar"
        }), 400

    valores.append(id)

    cursor = mysql.connection.cursor()

    try:
        sql = f"""
            UPDATE proyectos
            SET {', '.join(campos)}
            WHERE idproyecto=%s
        """

        cursor.execute(sql, tuple(valores))
        mysql.connection.commit()

        if cursor.rowcount == 0:
            cursor.execute(
                "SELECT idproyecto FROM proyectos WHERE idproyecto=%s",
                (id,)
            )

            if cursor.fetchone() is None:
                return jsonify({
                    "resultado": "Proyecto no encontrado"
                }), 404

        return jsonify({
            "resultado": "Proyecto actualizado correctamente"
        }), 200

    except Exception as e:
        mysql.connection.rollback()
        print("Error al actualizar proyecto:", e)

        return jsonify({
            "resultado": "No se pudo actualizar el proyecto",
            "error": "No se pudo completar la operación. Intentá nuevamente."
        }), 400

    finally:
        cursor.close()


####################### ELIMINAR PROYECTO ##############################

@app.route("/eliminar_proyecto/<int:id>", methods=["DELETE"])
@cross_origin()
def eliminar_proyecto(id):
    cursor = mysql.connection.cursor()

    try:
        cursor.execute(
            "DELETE FROM proyectos WHERE idproyecto=%s",
            (id,)
        )

        mysql.connection.commit()

        if cursor.rowcount == 0:
            return jsonify({
                "resultado": "Proyecto no encontrado"
            }), 404

        return jsonify({
            "resultado": "Proyecto eliminado correctamente"
        }), 200

    except Exception as e:
        mysql.connection.rollback()
        print("Error al eliminar proyecto:", e)

        return jsonify({
            "resultado": (
                "No se pudo eliminar el proyecto. "
                "Puede tener destinatarios u otros registros asociados."
            ),
            "error": "No se pudo completar la operación. Intentá nuevamente."
        }), 400

    finally:
        cursor.close()
        
####################### GESTION PROYECTOS Y DESTINATARIOS ##############################

####################### ASIGNAR DESTINATARIO A PROYECTO ##############################

@app.route("/asignar_destinatario_proyecto", methods=["POST"])
@cross_origin()
def asignar_destinatario_proyecto():

    destinatarios_dni = request.json["destinatarios_dni"]
    proyectos_idproyecto = request.json["proyectos_idproyecto"]

    cursor = mysql.connection.cursor()

    # Permitir reintentar una asignación sin crear otra fila para el mismo par.
    cursor.execute(
        "SELECT id FROM destinatario_proyecto "
        "WHERE destinatarios_dni=%s AND proyectos_idproyecto=%s LIMIT 1",
        (destinatarios_dni, proyectos_idproyecto)
    )
    existente = cursor.fetchone()
    if existente:
        cursor.close()
        return jsonify({"resultado": "El destinatario ya está asignado", "id": existente[0]})

    sql = """
    INSERT INTO destinatario_proyecto
    (
        destinatarios_dni,
        proyectos_idproyecto
    )
    VALUES (%s,%s)
    """

    cursor.execute(sql, (
        destinatarios_dni,
        proyectos_idproyecto
    ))

    mysql.connection.commit()
    cursor.close()

    return jsonify({
        "resultado": "Destinatario asignado correctamente"
    })


############################ TRAER DESTINATARIOS DE UN PROYECTO ###########################

@app.route(
    "/traer_destinatarios_proyecto/<int:idproyecto>",
    methods=["GET"]
)
@cross_origin()
def traer_destinatarios_proyecto(idproyecto):
    cursor = mysql.connection.cursor()

    try:
        cursor.execute("""
            SELECT
                d.dni,
                d.nombres,
                d.apellidos,
                dp.id
            FROM destinatarios AS d
            INNER JOIN destinatario_proyecto AS dp
                ON dp.destinatarios_dni = d.dni
            WHERE dp.proyectos_idproyecto = %s
            ORDER BY d.apellidos, d.nombres
        """, (idproyecto,))

        filas = cursor.fetchall()

        destinatarios = []

        for fila in filas:
            destinatarios.append({
                "dni": fila[0],
                "nombres": fila[1],
                "apellidos": fila[2],
                "id": fila[3],
                "nombre": f"{fila[1]} {fila[2]}"
            })

        return jsonify(destinatarios), 200

    except Exception as e:
        app.logger.exception(
            "Error al cargar destinatarios del proyecto"
        )

        return jsonify({
            "error": "No se pudo completar la operación. Intentá nuevamente."
        }), 500

    finally:
        cursor.close()


############################ ACTUALIZAR DESTINATARIO DE PROYECTO ############################

@app.route("/actualizar_destinatario_proyecto/<int:id>", methods=["PUT"])
@cross_origin()
def actualizar_destinatario_proyecto(id):

    datos = request.json

    campos = []
    valores = []

    if "destinatarios_dni" in datos:
        campos.append("destinatarios_dni=%s")
        valores.append(datos["destinatarios_dni"])

    if "proyectos_idproyecto" in datos:
        campos.append("proyectos_idproyecto=%s")
        valores.append(datos["proyectos_idproyecto"])

    if len(campos) == 0:
        return jsonify({
            "resultado": "No se enviaron datos para actualizar"
        }), 400

    sql = f"""
    UPDATE destinatario_proyecto
    SET {', '.join(campos)}
    WHERE id=%s
    """

    valores.append(id)

    cursor = mysql.connection.cursor()
    cursor.execute(sql, tuple(valores))

    mysql.connection.commit()
    cursor.close()

    return jsonify({
        "resultado": "Asignación actualizada correctamente"
    })


############################ ELIMINAR DESTINATARIO DE PROYECTO ############################

@app.route("/eliminar_destinatario_proyecto/<int:id>", methods=["DELETE"])
@cross_origin()
def eliminar_destinatario_proyecto(id):

    cursor = mysql.connection.cursor()

    cursor.execute(
        "DELETE FROM destinatario_proyecto WHERE id=%s",
        (id,)
    )

    mysql.connection.commit()
    cursor.close()

    return jsonify({
        "resultado": "Asignación eliminada correctamente"
    })


####################### GESTION SESIONES DE ASISTENCIA #######################

# =========================================================
# CREAR SESIÓN DE ASISTENCIA
# =========================================================

@app.route("/nueva_sesion", methods=["POST"])
@cross_origin()
def nueva_sesion():

    datos = request.get_json(silent=True) or {}

    try:
        proyectos_idproyecto = cuentas.entero(datos.get("proyectos_idproyecto"), 1)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    # The author comes from the signed session, never from a client-supplied ID.
    usuario_idusuario = g.usuario_actual["idusuario"]

    if not proyectos_idproyecto or not usuario_idusuario:
        return jsonify({
            "error": "El proyecto y el usuario son obligatorios"
        }), 400

    cursor = mysql.connection.cursor()

    try:
        cursor.execute(
            "SELECT idproyecto FROM proyectos WHERE idproyecto = %s",
            (proyectos_idproyecto,)
        )

        if cursor.fetchone() is None:
            return jsonify({
                "error": "El proyecto no existe"
            }), 404

        cursor.execute(
            "SELECT idusuario FROM usuario WHERE idusuario = %s",
            (usuario_idusuario,)
        )

        if cursor.fetchone() is None:
            return jsonify({
                "error": "El usuario no existe"
            }), 404

        fecha = datetime.now(
            ZoneInfo("America/Argentina/Buenos_Aires")
        )

        cursor.execute(
            """
            INSERT INTO sesiones_asistencia
                (fecha, proyectos_idproyecto, usuario_idusuario)
            VALUES (%s, %s, %s)
            """,
            (
                fecha,
                proyectos_idproyecto,
                usuario_idusuario
            )
        )

        id_sesion = cursor.lastrowid

        confirmar_transaccion(mysql)

        return jsonify({
            "resultado": "Sesión creada correctamente",
            "idsesion": id_sesion
        }), 201

    except Exception as e:
        mysql.connection.rollback()
        app.logger.exception("Error al crear sesión de asistencia")

        return jsonify({
            "error": "No se pudo completar la operación. Intentá nuevamente."
        }), 500

    finally:
        cursor.close()


# =========================================================
# TRAER TODAS LAS SESIONES
# =========================================================

@app.route("/traer_sesiones", methods=["GET"])
@cross_origin()
def traer_sesiones():

    cursor = mysql.connection.cursor()

    try:
        proyecto = request.args.get("proyecto")
        filtro = " WHERE s.proyectos_idproyecto = %s " if proyecto else ""
        valores = (cuentas.entero(proyecto, 1),) if proyecto else ()
        cursor.execute(
            """
            SELECT
                s.idsesion,
                s.fecha,
                s.proyectos_idproyecto,
                p.nombre,
                s.usuario_idusuario,
                u.nombre
            FROM sesiones_asistencia s
            INNER JOIN proyectos p
                ON s.proyectos_idproyecto = p.idproyecto
            INNER JOIN usuario u
                ON s.usuario_idusuario = u.idusuario
            """ + filtro + " ORDER BY s.fecha DESC,s.idsesion DESC", valores
        )

        filas = cursor.fetchall()

        sesiones = []

        for fila in filas:
            sesiones.append({
                "idsesion": fila[0],
                "fecha": fila[1].isoformat() if fila[1] else None,
                "proyectos_idproyecto": fila[2],
                "proyecto": fila[3],
                "usuario_idusuario": fila[4],
                "usuario": fila[5]
            })

        return jsonify(sesiones), 200

    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        app.logger.exception("Error al consultar sesiones")

        return jsonify({
            "error": "No se pudo completar la operación. Intentá nuevamente."
        }), 500

    finally:
        cursor.close()


# =========================================================
# TRAER UNA SESIÓN
# =========================================================

@app.route("/traer_sesion/<int:idsesion>", methods=["GET"])
@cross_origin()
def traer_sesion(idsesion):

    cursor = mysql.connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                s.idsesion,
                s.fecha,
                s.proyectos_idproyecto,
                p.nombre,
                s.usuario_idusuario,
                u.nombre
            FROM sesiones_asistencia s
            INNER JOIN proyectos p
                ON s.proyectos_idproyecto = p.idproyecto
            INNER JOIN usuario u
                ON s.usuario_idusuario = u.idusuario
            WHERE s.idsesion = %s
            """,
            (idsesion,)
        )

        fila = cursor.fetchone()

        if fila is None:
            return jsonify({
                "error": "Sesión no encontrada"
            }), 404

        return jsonify({
            "idsesion": fila[0],
            "fecha": fila[1].isoformat() if fila[1] else None,
            "proyectos_idproyecto": fila[2],
            "proyecto": fila[3],
            "usuario_idusuario": fila[4],
            "usuario": fila[5]
        }), 200

    except Exception as e:
        app.logger.exception("Error al consultar sesión")

        return jsonify({
            "error": "No se pudo completar la operación. Intentá nuevamente."
        }), 500

    finally:
        cursor.close()


# =========================================================
# GUARDAR ASISTENCIAS DE UNA SESIÓN
# =========================================================

@app.route("/guardar_asistencia", methods=["POST"])
@cross_origin()
def guardar_asistencia():

    return asistencias.guardar(mysql)


# =========================================================
# TRAER ASISTENCIAS DE UNA SESIÓN
# =========================================================

@app.route("/traer_asistencias/<int:idsesion>", methods=["GET"])
@cross_origin() 
def traer_asistencias(idsesion):

    cursor = mysql.connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                a.id,
                a.sesiones_idsesion,
                a.destinatarios_dni,
                d.nombres,
                d.apellidos,
                a.presente
            FROM asistencia a
            INNER JOIN destinatarios d
                ON a.destinatarios_dni = d.dni
            WHERE a.sesiones_idsesion = %s
            ORDER BY d.apellidos, d.nombres
            """,
            (idsesion,)
        )

        filas = cursor.fetchall()

        asistencias = []

        for fila in filas:
            asistencias.append({
                "id": fila[0],
                "sesiones_idsesion": fila[1],
                "dni": fila[2],
                "nombre": f"{fila[4]}, {fila[3]}",
                "presente": fila[5]
            })

        return jsonify(asistencias), 200

    except Exception as e:
        app.logger.exception("Error al consultar asistencias")

        return jsonify({
            "error": "No se pudo completar la operación. Intentá nuevamente."
        }), 500

    finally:
        cursor.close()


# =========================================================
# ACTUALIZAR ASISTENCIA
# =========================================================

@app.route("/actualizar_asistencia/<int:id>", methods=["PUT"])
@cross_origin()
def actualizar_asistencia(id):

    datos = request.get_json(silent=True) or {}

    if "presente" not in datos:
        return jsonify({
            "error": "Debe indicar si el destinatario estuvo presente"
        }), 400

    presente = datos["presente"]

    if presente not in (0, 1, False, True):
        return jsonify({
            "error": "El estado debe ser Presente o Ausente"
        }), 400

    cursor = mysql.connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE asistencia
            SET presente = %s
            WHERE id = %s
            """,
            (int(presente), id)
        )

        if cursor.rowcount == 0:
            cursor.execute(
                "SELECT id FROM asistencia WHERE id = %s",
                (id,)
            )

            if cursor.fetchone() is None:
                return jsonify({
                    "error": "Asistencia no encontrada"
                }), 404

        mysql.connection.commit()

        return jsonify({
            "resultado": "Asistencia actualizada correctamente"
        }), 200

    except Exception as e:
        mysql.connection.rollback()
        app.logger.exception("Error al actualizar asistencia")

        return jsonify({
            "error": "No se pudo completar la operación. Intentá nuevamente."
        }), 500

    finally:
        cursor.close()


# =========================================================
# ELIMINAR ASISTENCIA
# =========================================================

@app.route("/eliminar_asistencia/<int:id>", methods=["DELETE"])
@cross_origin()
def eliminar_asistencia(id):

    cursor = mysql.connection.cursor()

    try:
        cursor.execute(
            "DELETE FROM asistencia WHERE id = %s",
            (id,)
        )

        if cursor.rowcount == 0:
            mysql.connection.rollback()

            return jsonify({
                "error": "Asistencia no encontrada"
            }), 404

        mysql.connection.commit()

        return jsonify({
            "resultado": "Asistencia eliminada correctamente"
        }), 200

    except Exception as e:
        mysql.connection.rollback()
        app.logger.exception("Error al eliminar asistencia")

        return jsonify({
            "error": "No se pudo completar la operación. Intentá nuevamente."
        }), 500

    finally:
        cursor.close()


# =========================================================
# ELIMINAR SESIÓN Y SUS ASISTENCIAS
# =========================================================

@app.route("/eliminar_sesion/<int:idsesion>", methods=["DELETE"])
@cross_origin()
def eliminar_sesion(idsesion):

    cursor = mysql.connection.cursor()

    try:
        cursor.execute(
            """
            SELECT idsesion
            FROM sesiones_asistencia
            WHERE idsesion = %s
            """,
            (idsesion,)
        )

        if cursor.fetchone() is None:
            return jsonify({
                "error": "Sesión no encontrada"
            }), 404

        # Primero se eliminan los registros relacionados.
        cursor.execute(
            """
            DELETE FROM asistencia
            WHERE sesiones_idsesion = %s
            """,
            (idsesion,)
        )

        # Después se elimina la sesión.
        cursor.execute(
            """
            DELETE FROM sesiones_asistencia
            WHERE idsesion = %s
            """,
            (idsesion,)
        )

        mysql.connection.commit()

        return jsonify({
            "resultado": "Sesión y asistencias eliminadas correctamente"
        }), 200

    except Exception as e:
        mysql.connection.rollback()
        app.logger.exception("Error al eliminar sesión")

        return jsonify({
            "error": "No se pudo completar la operación. Intentá nuevamente."
        }), 500

    finally:
        cursor.close()


############################ TRAER ASISTENCIAS DE UNA SESION ############################
'''
@app.route("/traer_asistencias/int:idsesion", methods=["GET"])
@cross_origin()
def traer_asistencias(idsesion):

    sql = """
    SELECT
        a.id,
        a.sesiones_idsesion,
        a.destinatarios_dni,
        CONCAT(d.apellidos, ', ', d.nombres),
        a.presente
    FROM asistencia a
    INNER JOIN destinatarios d
        ON a.destinatarios_dni = d.dni
    WHERE a.sesiones_idsesion=%s
    ORDER BY d.apellidos, d.nombres
    """

    cursor = mysql.connection.cursor()
    cursor.execute(sql, (idsesion,))

    resultado = cursor.fetchall()

    cursor.close()

    if len(resultado) == 0:
        return jsonify({
            "mensaje": "No hay asistencias para esta sesion"
        })

    asistencias = []

    for i in resultado:

        asistencias.append({

            "id": i[0],
            "sesiones_idsesion": i[1],
            "dni": i[2],
            "nombre": i[3],
            "presente": i[4]

        })

    return jsonify(asistencias)
'''

# =========================================================
# INICIO
# =========================================================


@app.get("/traer_asignaciones")
def traer_asignaciones():
    return consultas.asignaciones(mysql)

@app.before_request
def validar_cuerpo_json():
    if request.is_json and request.method in {"POST", "PUT", "DELETE"}:
        if not isinstance(request.get_json(silent=True), dict):
            return jsonify(error="Enviá un objeto JSON válido."), 400

app.view_functions["insertar_anuncio"] = idempotente(mysql, "crear_anuncio")(app.view_functions["insertar_anuncio"])
app.view_functions["nueva_sesion"] = idempotente(mysql, "crear_asistencia")(app.view_functions["nueva_sesion"])

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
