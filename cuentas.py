"""Account mutations and revocation share the same database transaction."""
from flask import current_app, g, jsonify, request
from credenciales import comprobar_clave, crear_hash, es_hash, validar_clave
from seguridad import GESTORES, ROLES, emitir_token, normalizar_rol, revocar_sesiones


def datos_json():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        raise ValueError("Enviá un objeto JSON válido.")
    return datos


def entero(valor, minimo=0, maximo=2147483647):
    if isinstance(valor, bool) or not isinstance(valor, (int, str)):
        raise ValueError("Se requiere un número entero.")
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        raise ValueError("Se requiere un número entero.")
    if not minimo <= numero <= maximo:
        raise ValueError("El número está fuera del rango permitido.")
    return numero


def texto(valor, nombre, maximo=150):
    if not isinstance(valor, str) or not valor.strip() or len(valor.strip()) > maximo:
        raise ValueError(f"Revisá el campo {nombre} (máximo {maximo} caracteres).")
    return valor.strip()


def bloquear_cuentas(cursor):
    # One consistent lock order protects the final active manager from concurrent edits.
    cursor.execute("SELECT idusuario,perfil,activo FROM usuario ORDER BY idusuario FOR UPDATE")
    return cursor.fetchall()


def preservar_gestor(filas, idusuario, perfil, activo):
    actual = next((fila for fila in filas if fila[0] == idusuario), None)
    if actual is None:
        return jsonify(resultado="Usuario no encontrado"), 404
    era_gestor = actual[2] == 1 and normalizar_rol(actual[1]) in GESTORES
    sera_gestor = activo == 1 and normalizar_rol(perfil) in GESTORES
    if era_gestor and not sera_gestor and sum(f[2] == 1 and normalizar_rol(f[1]) in GESTORES for f in filas) <= 1:
        return jsonify(codigo="ultimo_gestor", resultado="Debe quedar al menos un administrador o referente activo."), 409
    return None


def registrar(mysql):
    cursor = None
    try:
        datos = datos_json()
        nombre = texto(datos.get("nombre"), "nombre", 45)
        apellido = texto(datos.get("apellido"), "apellido", 45)
        mail = texto(datos.get("mail"), "correo", 254)
        if "@" not in mail or "." not in mail.rsplit("@", 1)[-1]:
            raise ValueError("Ingresá un correo válido.")
        perfil = normalizar_rol(datos.get("perfil"))
        gestor = getattr(g, "rol_actual", None) in GESTORES
        if perfil not in (ROLES if gestor else {"voluntario", "referente"}):
            raise ValueError("El perfil de registro no es válido.")
        clave = datos.get("clave")
        if not validar_clave(clave):
            raise ValueError("La contraseña debe tener entre 8 y 128 caracteres, mayúscula, minúscula, número y símbolo.")
        activo = entero(datos.get("activo", 0), 0, 1) if gestor else 0
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT idusuario FROM usuario WHERE mail=%s", (mail,))
        if cursor.fetchone() is not None:
            return jsonify(resultado="El correo ya está registrado"), 409
        cursor.execute("INSERT INTO usuario (nombre,apellido,mail,clave,perfil,activo) VALUES (%s,%s,%s,%s,%s,%s)",
                       (nombre, apellido, mail, crear_hash(clave), perfil, activo))
        mysql.connection.commit()
        return jsonify(resultado="Usuario registrado. Pendiente de activación." if not activo else "Usuario registrado y activo."), 201
    except ValueError as error:
        return jsonify(resultado=str(error)), 400
    except Exception:
        mysql.connection.rollback()
        current_app.logger.exception("No se pudo registrar el usuario")
        return jsonify(resultado="No se pudo registrar el usuario."), 503
    finally:
        if cursor is not None:
            cursor.close()


def modificar(mysql, idusuario, estado=None, eliminar=False):
    cursor = None
    try:
        idusuario = entero(idusuario, 1)
        datos = {} if estado is not None or eliminar else datos_json()
        campos, valores = [], []
        for campo in ("nombre", "apellido", "mail"):
            if campo in datos:
                valores.append(texto(datos[campo], campo, 254 if campo == "mail" else 45))
                campos.append(f"{campo}=%s")
        if "clave" in datos:
            if not validar_clave(datos["clave"]):
                raise ValueError("La contraseña debe tener entre 8 y 128 caracteres, mayúscula, minúscula, número y símbolo.")
            campos.append("clave=%s")
            valores.append(crear_hash(datos["clave"]))
        if "perfil" in datos:
            perfil = normalizar_rol(datos["perfil"])
            if perfil not in ROLES:
                raise ValueError("El perfil no es válido.")
            campos.append("perfil=%s")
            valores.append(perfil)
        if estado is not None or "activo" in datos:
            campos.append("activo=%s")
            valores.append(entero(estado if estado is not None else datos["activo"], 0, 1))
        if not campos and not eliminar:
            raise ValueError("No se enviaron datos para actualizar.")
        cursor = mysql.connection.cursor()
        filas = bloquear_cuentas(cursor)
        actual = next((fila for fila in filas if fila[0] == idusuario), None)
        if actual is None:
            mysql.connection.rollback()
            return jsonify(resultado="Usuario no encontrado"), 404
        perfil = datos.get("perfil", actual[1])
        activo = 0 if eliminar else (estado if estado is not None else datos.get("activo", actual[2]))
        rechazo = preservar_gestor(filas, idusuario, perfil, int(activo))
        if rechazo:
            mysql.connection.rollback()
            return rechazo
        if eliminar:
            cursor.execute("DELETE FROM usuario WHERE idusuario=%s", (idusuario,))
        else:
            cursor.execute("UPDATE usuario SET " + ", ".join(campos) + " WHERE idusuario=%s", (*valores, idusuario))
        if eliminar or estado is not None or any(c in datos for c in ("clave", "perfil", "mail", "activo")):
            revocar_sesiones(cursor, idusuario)
        mysql.connection.commit()
        return jsonify(resultado="Usuario eliminado correctamente" if eliminar else "Usuario actualizado correctamente")
    except ValueError as error:
        return jsonify(resultado=str(error)), 400
    except Exception:
        mysql.connection.rollback()
        current_app.logger.exception("No se pudo actualizar el usuario")
        return jsonify(resultado="No se pudo actualizar el usuario. Revisá sus datos y registros asociados."), 409
    finally:
        if cursor is not None:
            cursor.close()


def iniciar(mysql):
    cursor = None
    try:
        if not current_app.config.get("SECRET_KEY"):
            return jsonify(resultado="El servidor debe configurar su clave de sesión.", codigo="seguridad_no_configurada"), 503
        datos = datos_json()
        mail = texto(datos.get("mail"), "correo", 254)
        clave = datos.get("clave")
        if not isinstance(clave, str) or not 1 <= len(clave) <= 1024:
            raise ValueError("Ingresá la contraseña.")
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT idusuario,nombre,apellido,mail,clave,perfil,activo FROM usuario WHERE mail=%s FOR UPDATE", (mail,))
        fila = cursor.fetchone()
        if fila is None or not comprobar_clave(fila[4], clave):
            mysql.connection.rollback()
            return jsonify(resultado="El correo o la contraseña son incorrectos."), 401
        if fila[6] != 1:
            mysql.connection.rollback()
            return jsonify(resultado="El usuario no está activo", codigo="cuenta_deshabilitada"), 403
        if not es_hash(fila[4]):
            cursor.execute("UPDATE usuario SET clave=%s WHERE idusuario=%s", (crear_hash(clave), fila[0]))
            revocar_sesiones(cursor, fila[0])
        token = emitir_token(current_app, fila[0], datos.get("recordarme") is True, cursor=cursor)
        mysql.connection.commit()
        return jsonify(resultado="Inicio de sesión correcto", token=token,
                       usuario=dict(zip(("idusuario", "nombre", "apellido", "mail", "perfil", "activo"), (*fila[:4], *fila[5:]))))
    except ValueError as error:
        return jsonify(resultado=str(error)), 400
    except Exception:
        mysql.connection.rollback()
        current_app.logger.exception("No se pudo iniciar sesión")
        return jsonify(resultado="No se pudo iniciar sesión. Verificá la migración y la conexión del servidor."), 503
    finally:
        if cursor is not None:
            cursor.close()
