"""Authentication and authorization shared by every API endpoint."""
from flask import g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
import hashlib
import secrets

GESTORES = {"administrador", "admin", "referente"}
ROLES = GESTORES | {"voluntario"}
LECTURAS_VOLUNTARIO = {
    "sesion_actual", "listar_anuncios", "traer_proyectos", "traer_inventario",
    "traer_inventario_proyecto", "traer_destinatarios_proyecto", "traer_sesiones",
    "traer_sesion", "traer_asistencias",
}
ESCRITURAS_VOLUNTARIO = {"nueva_sesion", "guardar_asistencia", "cerrar_sesion"}


def normalizar_rol(valor):
    return str(valor or "").strip().lower()


def emitir_token(app, idusuario, recordar=False, cursor=None):
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("Falta configurar SECRET_KEY")
    duracion = 30 * 24 * 3600 if recordar else 12 * 3600
    sid = secrets.token_urlsafe(32)
    propio = cursor is None
    if propio:
        cursor = app.extensions["auth_mysql"].connection.cursor()
    try:
        cursor.execute("INSERT INTO sesiones_usuario (token_hash,idusuario,expira) VALUES (%s,%s,TIMESTAMPADD(SECOND,%s,UTC_TIMESTAMP()))",
                       (hashlib.sha256(sid.encode()).hexdigest(), int(idusuario), duracion))
        if propio:
            app.extensions["auth_mysql"].connection.commit()
        return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="sesion-voluntariado-v2").dumps(
            {"id": int(idusuario), "duracion": duracion, "sid": sid}
        )
    finally:
        if propio:
            cursor.close()


def revocar_sesiones(cursor, idusuario):
    cursor.execute("UPDATE sesiones_usuario SET revocada=1 WHERE idusuario=%s", (idusuario,))


def instalar_seguridad(app, mysql):
    app.extensions["auth_mysql"] = mysql
    @app.before_request
    def verificar_acceso():
        # Preflight must remain public for the Android WebView and browser.
        if request.method == "OPTIONS" or request.endpoint is None:
            return None
        if request.endpoint in {"iniciar_sesion", "obtener_imagen"}:
            return None
        if request.endpoint == "insertar_usuario_voluntariado" and not request.headers.get("Authorization"):
            return None
        if not app.config.get("SECRET_KEY"):
            return jsonify(codigo="seguridad_no_configurada", resultado="El servidor debe configurar su clave de sesión."), 503
        cabecera = request.headers.get("Authorization", "")
        if not cabecera.startswith("Bearer "):
            return jsonify(codigo="sesion_invalida", resultado="Iniciá sesión nuevamente."), 401
        try:
            firmante = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="sesion-voluntariado-v2")
            datos = firmante.loads(cabecera[7:], max_age=30 * 24 * 3600)
            duracion = datos.get("duracion")
            if duracion not in (12 * 3600, 30 * 24 * 3600):
                raise BadSignature("Duración inválida")
            datos = firmante.loads(cabecera[7:], max_age=duracion)
            idusuario = int(datos["id"])
            sid = datos["sid"]
            if not isinstance(sid, str) or not 32 <= len(sid) <= 80:
                raise BadSignature("Sesión inválida")
            token_hash = hashlib.sha256(sid.encode()).hexdigest()
        except (BadSignature, SignatureExpired, ValueError, TypeError, KeyError, AttributeError):
            return jsonify(codigo="sesion_invalida", resultado="Tu sesión venció. Iniciá sesión nuevamente."), 401

        cursor = None
        try:
            cursor = mysql.connection.cursor()
            cursor.execute("""SELECT u.idusuario,u.nombre,u.apellido,u.mail,u.perfil,u.activo,
                CASE WHEN s.token_hash IS NOT NULL AND s.revocada=0 AND s.expira>UTC_TIMESTAMP() THEN 1 ELSE 0 END
                FROM usuario u LEFT JOIN sesiones_usuario s ON s.idusuario=u.idusuario AND s.token_hash=%s
                WHERE u.idusuario=%s""", (token_hash, idusuario))
            fila = cursor.fetchone()
        except Exception:
            app.logger.exception("No se pudo verificar la sesión")
            return jsonify(codigo="verificacion_no_disponible", resultado="No se pudo verificar la sesión. Intentá nuevamente."), 503
        finally:
            if cursor is not None:
                cursor.close()
        if fila is None or fila[5] != 1:
            return jsonify(codigo="cuenta_deshabilitada", resultado="Su cuenta se deshabilitó. Contacte a un administrador."), 403
        if fila[6] != 1:
            return jsonify(codigo="sesion_invalida", resultado="Su sesión se cerró. Inicie sesión nuevamente."), 401
        g.token_hash = token_hash
        g.usuario_actual = dict(zip(("idusuario", "nombre", "apellido", "mail", "perfil", "activo"), fila))
        g.rol_actual = normalizar_rol(fila[4])
        if g.rol_actual not in ROLES:
            return jsonify(codigo="sin_permisos", resultado="Tu cuenta no tiene un rol autorizado."), 403
        if g.rol_actual in GESTORES:
            return None
        lectura = request.method == "GET" and request.endpoint in LECTURAS_VOLUNTARIO
        escritura = request.method == "POST" and request.endpoint in ESCRITURAS_VOLUNTARIO
        if not (lectura or escritura):
            return jsonify(codigo="sin_permisos", resultado="No tenés permiso para realizar esta operación."), 403
        return None

    @app.after_request
    def evitar_cache_privada(respuesta):
        if request.endpoint != "obtener_imagen":
            respuesta.headers["Cache-Control"] = "no-store"
        return respuesta

    @app.post("/cerrar_sesion")
    def cerrar_sesion():
        cursor = mysql.connection.cursor()
        try:
            cursor.execute("UPDATE sesiones_usuario SET revocada=1 WHERE token_hash=%s AND idusuario=%s",
                           (g.token_hash, g.usuario_actual["idusuario"]))
            mysql.connection.commit()
            return jsonify(resultado="Sesión cerrada")
        except Exception:
            mysql.connection.rollback()
            return jsonify(resultado="No se pudo cerrar la sesión. Reintentá."), 503
        finally:
            cursor.close()

    @app.get("/sesion_actual")
    def sesion_actual():
        respuesta = jsonify(usuario=g.usuario_actual)
        respuesta.headers["Cache-Control"] = "no-store"
        return respuesta
