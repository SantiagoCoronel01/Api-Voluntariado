"""Offline migration: defaults to inspection. --apply is explicitly required."""
import argparse
from credenciales import crear_hash, es_hash


def migrar(conexion, aplicar=False):
    cursor = conexion.cursor()
    actualizadas = 0
    try:
        cursor.execute("SELECT idusuario, clave FROM usuario")
        filas = cursor.fetchall()
        pendientes = sum(not es_hash(clave) for _, clave in filas)
        if aplicar:
            for idusuario, clave in filas:
                if not es_hash(clave):
                    cursor.execute("UPDATE usuario SET clave=%s WHERE idusuario=%s AND clave=%s",
                                   (crear_hash(clave), idusuario, clave))
                    actualizadas += cursor.rowcount
                    cursor.execute("UPDATE sesiones_usuario SET revocada=1 WHERE idusuario=%s", (idusuario,))
            conexion.commit()
        return pendientes, actualizadas
    except Exception:
        conexion.rollback()
        raise
    finally:
        cursor.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrar contraseñas sin imprimir credenciales")
    parser.add_argument("--apply", action="store_true", help="Aplicar luego del respaldo y la migración SQL")
    args = parser.parse_args()
    from app import app, mysql
    with app.app_context():
        pendientes, actualizadas = migrar(mysql.connection, args.apply)
        print(f"Cuentas pendientes: {pendientes}. Cuentas migradas: {actualizadas}.")
