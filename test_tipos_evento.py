import unittest
from anuncios_validacion import TIPOS, normalizar_tipo_evento, validar_anuncio


class TiposEventoTest(unittest.TestCase):
    def test_normaliza_la_categoria_antigua_solo_para_lectura(self):
        self.assertEqual(normalizar_tipo_evento('Medio Ambiente'), 'Información')
        self.assertEqual(normalizar_tipo_evento('Donaciones'), 'Donaciones')

    def test_solo_admite_los_tres_tipos_actuales(self):
        self.assertEqual(TIPOS, {'Donaciones', 'Actividades', 'Información'})
        for tipo in TIPOS:
            validar_anuncio({'titulo': 'Jornada', 'descripcion': 'Una actividad',
                             'tipo_evento': tipo, 'fecha_evento': '2026-10-24 17:00:00'})

    def test_rechaza_medio_ambiente_en_altas_y_ediciones(self):
        for parcial in (False, True):
            with self.subTest(parcial=parcial), self.assertRaises(ValueError):
                validar_anuncio({'titulo': 'Jornada', 'descripcion': 'Una actividad',
                                 'tipo_evento': 'Medio Ambiente', 'fecha_evento': '2026-10-24 17:00:00'}, parcial=parcial)
