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


#AGREGAR USUARIOS
@app.route("/nuevo_usuario_voluntariado", methods=["POST"])
@cross_origin()
def insertar_usuario_voluntariado():
    nombre = request.json["nombre"]
    mail = request.json["mail"]
    clave = request.json["clave"]
    perfil = request.json["perfil"]


    cursor = mysql.connection.cursor()

    sql = "INSERT INTO usuario(nombre, mail, clave, perfil) values(%s, %s, %s, %s);"
    cursor.execute(sql, (nombre, mail, clave, perfil))


    mysql.connection.commit()

    cursor.close()
    response = make_response()

    response = jsonify({"resultado":"Agregado nuevo usuario"})
    return response

###TRAER USUARIOS
@app.route("/traer_usuarios_voluntariado", methods=["GET"])
@cross_origin()
def listar_usuarios_voluntariado():
    #consulta SQL
    sql = "SELECT idusuario, nombre, mail, mail, clave, perfil FROM usuario"

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

            p = {"idusuario":i[0], "nombre":i[1], "mail":i[2], "clave":i[3], "clave":i[4]}
            usuarios.append(p)

        return jsonify(usuarios)



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    



