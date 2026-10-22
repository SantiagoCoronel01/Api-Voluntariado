"""Password hashing and validation. Never log or return the credential."""
import hmac
from werkzeug.security import check_password_hash, generate_password_hash


def es_hash(valor):
    return isinstance(valor, str) and valor.startswith(("scrypt:", "pbkdf2:"))


def validar_clave(clave):
    if not isinstance(clave, str) or not 8 <= len(clave) <= 128:
        return False
    return (any(c.isupper() for c in clave) and any(c.islower() for c in clave)
            and any(c.isdigit() for c in clave) and any(not c.isalnum() for c in clave))


def crear_hash(clave):
    return generate_password_hash(clave, method="scrypt")


def comprobar_clave(guardada, recibida):
    if not isinstance(guardada, str) or not isinstance(recibida, str):
        return False
    if es_hash(guardada):
        try:
            return check_password_hash(guardada, recibida)
        except (ValueError, TypeError):
            return False
    # Compatibility only during migration; a successful login upgrades this value.
    return hmac.compare_digest(guardada.encode("utf-8"), recibida.encode("utf-8"))
