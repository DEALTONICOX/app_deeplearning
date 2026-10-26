"""Contrato del motor nuevo y compatibilidad; la calidad se mide por pliegues aparte."""
import io
import json
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from fastapi.testclient import TestClient

import app as servicio
from motor_rostros import normalizar, puntuar


class RostrosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directorio_anterior = servicio.DIRECTORIO_MODELO
        servicio.DIRECTORIO_MODELO = Path('salidas_mejoradas')
        cls.cliente = TestClient(servicio.app)
        cls.cliente.__enter__()
        auditoria = json.loads((servicio.DIRECTORIO_MODELO/'auditoria_dataset.json').read_text(encoding='utf-8'))
        cls.fotos = {}
        for a in auditoria['archivos']:
            cls.fotos.setdefault(a['nombre'], Path(a['ruta']))
        buffer = io.BytesIO()
        Image.new('RGB',(400,400),'white').save(buffer,format='PNG')
        cls.blanco = buffer.getvalue()

    @classmethod
    def tearDownClass(cls):
        cls.cliente.__exit__(None,None,None)
        servicio.DIRECTORIO_MODELO = cls.directorio_anterior

    def enviar(self, contenidos):
        return self.cliente.post('/predecir-fotos/',files=[('archivos',('foto.jpg',c,'image/jpeg')) for c in contenidos])

    def test_contrato_nueve_identidades(self):
        salud = self.cliente.get('/salud').json()
        self.assertEqual(salud['motor'],'sface')
        self.assertEqual(salud['personas_en_base_de_datos'],9)
        for nombre,ruta in self.fotos.items():
            with self.subTest(nombre=nombre):
                respuesta=self.enviar([ruta.read_bytes()])
                self.assertEqual(respuesta.status_code,200)
                self.assertEqual(respuesta.json()['nombre'],nombre)
                self.assertEqual(respuesta.json()['tipo_puntuacion'],'similitud_coseno')

    def test_sin_rostro_y_mayoria_sin_rostro(self):
        for contenidos in ([self.blanco], [next(iter(self.fotos.values())).read_bytes(),self.blanco,self.blanco]):
            datos=self.enviar(contenidos).json()
            self.assertFalse(datos['identificado'])
            self.assertFalse(datos['rostro_detectado'])

    def test_lote_coherente_y_lote_con_tres_identidades(self):
        nombres=list(self.fotos)
        foto=self.fotos[nombres[0]].read_bytes()
        datos=self.enviar([foto]*3).json()
        self.assertEqual(datos['nombre'],nombres[0])
        self.assertTrue(datos['consenso'])
        mezclado=self.enviar([self.fotos[n].read_bytes() for n in nombres[:3]]).json()
        self.assertFalse(mezclado['identificado'])

    def test_candidatos_parecidos_no_se_aceptan(self):
        scores=np.zeros(9,dtype=np.float32)
        scores[:2]=[0.8,0.79]
        respuesta=servicio._responder(scores,1,1)
        self.assertFalse(respuesta.identificado)
        self.assertLess(respuesta.margen,respuesta.margen_minimo)

    def test_entradas_invalidas(self):
        self.assertEqual(self.enviar([b'no es una foto']).status_code,400)
        self.assertEqual(self.enviar([self.blanco]*6).status_code,422)
        self.assertEqual(self.cliente.post('/predecir-matriz/',json={'matriz':[[[0,0,0]]]}).status_code,422)

    def test_matriz_legacy(self):
        # Una matriz uniforme debe seguir rechazándose al usar el motor nuevo.
        respuesta=self.cliente.post('/predecir-matriz/',json={'matriz':np.full((128,128,3),255).tolist()})
        self.assertEqual(respuesta.status_code,200)
        self.assertFalse(respuesta.json()['identificado'])


if __name__=='__main__':
    unittest.main(verbosity=2)
