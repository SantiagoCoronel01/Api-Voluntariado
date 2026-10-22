from datetime import datetime

MAX_DESCRIPCION = 5000
TIPOS = {"Donaciones", "Actividades", "Información"}


def normalizar_tipo_evento(tipo):
    return "Información" if tipo == "Medio Ambiente" else tipo


def validar_anuncio(datos, parcial=False):
    for campo, limite in (("titulo", 150), ("descripcion", MAX_DESCRIPCION)):
        if parcial and campo not in datos:
            continue
        valor = datos.get(campo)
        if not isinstance(valor, str) or not valor.strip() or len(valor) > limite:
            raise ValueError(f"El campo {campo} es obligatorio y admite hasta {limite} caracteres.")
    if not parcial or "tipo_evento" in datos:
        if datos.get("tipo_evento") not in TIPOS:
            raise ValueError("Seleccioná un tipo de evento válido.")
    if not parcial or "fecha_evento" in datos:
        valor = datos.get("fecha_evento")
        try:
            fecha = datetime.fromisoformat(valor)
            if fecha.tzinfo is not None:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("Ingresá una fecha y hora válidas sin conversión de zona horaria.")
