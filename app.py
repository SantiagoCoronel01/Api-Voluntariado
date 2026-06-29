from flask import Flask, request, jsonify
from flask.helpers import make_response
from flask_mysqldb import MySQL
from flask_cors import CORS, cross_origin


# para subir archivos
import os
#from werkzeug.utils import secure_filename


app = Flask(__name__)

import os

app.config["MYSQL_HOST"] = os.environ.get("DB_HOST")
app.config["MYSQL_USER"] = os.environ.get("DB_USER")
app.config["MYSQL_PASSWORD"] = os.environ.get("DB_PASSWORD")
app.config["MYSQL_DB"] = os.environ.get("DB_NAME")

mysql = MySQL(app)

CORS(app)

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
    cursor = mysql.connection.cursor()#mysql.connect.cursor()
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

            p = {"id":i[0], "nombre":i[1], "apellido":i[2], "provincia":i[3]}
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

#######################GESTION USUARIOS##############################
#AGREGAR USUARIOS
@app.route("/nuevo_usuario_voluntariado", methods=["POST"])
@cross_origin()
def insertar_usuario_voluntariado():

    nombre = request.json["nombre"]
    mail = request.json["mail"]
    clave = request.json["clave"]
    perfil = request.json["perfil"]

    cursor = mysql.connection.cursor()

    sql = """
    INSERT INTO usuario(nombre, mail, clave, perfil, activo)
    VALUES (%s, %s, %s, %s, 0)
    """

    cursor.execute(sql, (nombre, mail, clave, perfil))

    mysql.connection.commit()
    cursor.close()

    return jsonify({"resultado": "Usuario registrado. Pendiente de activación."})

###TRAER USUARIOS
@app.route("/traer_usuarios_voluntariado", methods=["GET"])
@cross_origin()
def listar_usuarios_voluntariado():

    sql = """
    SELECT idusuario, nombre, mail, clave, perfil, activo
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
            "mail": i[2],
            "clave": i[3],
            "perfil": i[4],
            "activo": i[5]
        })

    return jsonify(usuarios)

###ELIMINAR USUARIO
@app.route("/desactivar_usuario/<id>", methods=["PUT"])
@cross_origin()
def desactivar_usuario(id):

    sql = "UPDATE usuario SET activo = 0 WHERE idusuario = %s"

    cursor = mysql.connection.cursor()
    cursor.execute(sql, (id,))
    mysql.connection.commit()
    cursor.close()

    return jsonify({"resultado": "Usuario desactivado"})

### ACTIVAR USUARIO
@app.route("/activar_usuario/<id>", methods=["PUT"])
@cross_origin()
def activar_usuario(id):

    sql = "UPDATE usuario SET activo = 1 WHERE idusuario = %s"

    cursor = mysql.connection.cursor()
    cursor.execute(sql, (id,))
    mysql.connection.commit()
    cursor.close()

    return jsonify({"resultado": "Usuario activado"})

### ACTUALIZAR USUARIO
@app.route("/actualizar_usuario_voluntariado/<id>", methods=["PUT"])
@cross_origin()
def actualizar_usuario_voluntariado(id):

    datos = request.json

    campos = []
    valores = []

    if "nombre" in datos:
        campos.append("nombre=%s")
        valores.append(datos["nombre"])

    if "mail" in datos:
        campos.append("mail=%s")
        valores.append(datos["mail"])

    if "clave" in datos:
        campos.append("clave=%s")
        valores.append(datos["clave"])

    if "perfil" in datos:
        campos.append("perfil=%s")
        valores.append(datos["perfil"])

    if len(campos) == 0:
        return jsonify({"resultado": "No se enviaron datos para actualizar"}), 400

    sql = f"UPDATE usuario SET {', '.join(campos)} WHERE idusuario=%s"

    valores.append(id)

    cursor = mysql.connection.cursor()
    cursor.execute(sql, tuple(valores))
    mysql.connection.commit()
    cursor.close()

    return jsonify({"resultado": "Usuario actualizado correctamente"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    



