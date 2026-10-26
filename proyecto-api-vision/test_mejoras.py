"""Regresiones de auditoría, aumento y contrato de fotos. Ejecutar con unittest."""
import csv
import io
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
from tensorflow import keras

from auditar_dataset import auditar
from aumento_datos import construir_aumento
from entrenar_cnn import construir_cnn, construir_mobilenet, cargar_dataset
from preprocesamiento import lista_a_matriz
from app import app


class AuditoriaTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.imagenes = self.raiz / "images"
        self.csv = self.raiz / "sujetos.csv"
        with self.csv.open("w", encoding="utf-8", newline="") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow(["id_carpeta", "nombre_normalizado", "nombre_original"])
            for persona in range(3):
                identificador = f"p{persona}_01"
                escritor.writerow([identificador, f"persona_{persona}", f"Persona {persona}"])
                carpeta = self.imagenes / identificador
                carpeta.mkdir(parents=True)
                for numero in range(5):
                    Image.new("RGB", (80, 80), (persona * 70, numero * 40, 50)).save(carpeta / f"{numero}.png")

    def test_dataset_completo(self):
        informe = auditar(self.imagenes, self.csv)
        self.assertFalse(informe["errores"])
        self.assertEqual(informe["total_imagenes_unicas"], 15)
        X, y, nombres, _, _ = cargar_dataset(self.imagenes, self.csv)
        self.assertEqual(X.shape, (15, 128, 128, 3))
        self.assertEqual(len(nombres), 3)
        self.assertEqual(set(y), {0, 1, 2})

    def test_faltante_impide_entrenamiento(self):
        (self.imagenes / "p0_01/0.png").unlink()
        with self.assertRaisesRegex(ValueError, "al menos 5"):
            cargar_dataset(self.imagenes, self.csv)

    def test_duplicado_misma_persona_excluido(self):
        original = self.imagenes / "p0_01/0.png"
        original.with_name("copia.png").write_bytes(original.read_bytes())
        informe = auditar(self.imagenes, self.csv)
        self.assertFalse(informe["errores"])
        self.assertEqual(informe["total_imagenes_unicas"], 15)
        self.assertEqual(len(informe["duplicados"]), 1)

    def test_duplicado_otra_persona_impide_entrenamiento(self):
        (self.imagenes / "p1_01/copia.png").write_bytes((self.imagenes / "p0_01/0.png").read_bytes())
        self.assertTrue(any("identidades distintas" in e for e in auditar(self.imagenes, self.csv)["errores"]))


class AumentoTests(unittest.TestCase):
    def test_solo_entrenamiento_rango_y_serializacion(self):
        X = np.random.default_rng(42).random((2, 128, 128, 3), dtype=np.float32)
        aumento = construir_aumento()
        np.testing.assert_array_equal(aumento(X, training=False).numpy(), X)
        transformada = aumento(X, training=True).numpy()
        self.assertEqual(transformada.shape, X.shape)
        self.assertTrue(np.isfinite(transformada).all())
        self.assertGreaterEqual(transformada.min(), 0)
        self.assertLessEqual(transformada.max(), 1)
        self.assertFalse(np.array_equal(X, transformada))
        modelo = construir_cnn(3)
        modelo.compile(optimizer="adam", loss="sparse_categorical_crossentropy")
        self.assertTrue(np.isfinite(modelo.train_on_batch(X, np.array([0, 1]))))
        esperado = modelo(X, training=False).numpy()
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "modelo.keras"
            modelo.save(ruta)
            cargado = keras.models.load_model(ruta)
            np.testing.assert_allclose(cargado(X, training=False).numpy(), esperado, atol=1e-6)

    def test_mobilenet_respeta_control_sin_aumento(self):
        modelo, _ = construir_mobilenet(3, pesos=None, con_aumento=False)
        self.assertNotIn("aumento_rostros", [c.name for c in modelo.layers])
        self.assertEqual(modelo.output_shape[-1], 3)
        keras.backend.clear_session()

    def test_rechaza_pixeles_invalidos(self):
        for valor in (-1, 256, float("nan"), float("inf")):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                lista_a_matriz(np.full((128, 128, 3), valor), normalizada=False)


class FotosApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cliente = TestClient(app)
        cls.cliente.__enter__()
        buffer = io.BytesIO()
        Image.new("RGB", (300, 300), "white").save(buffer, format="PNG")
        cls.blanco = buffer.getvalue()

    @classmethod
    def tearDownClass(cls):
        cls.cliente.__exit__(None, None, None)

    def test_foto_y_lote_comparten_preprocesamiento(self):
        foto = Path("data/images/ge_01/ge_01_04.jpeg").read_bytes()
        una = self.cliente.post("/predecir/", files={"archivo": ("foto.jpg", foto, "image/jpeg")})
        lote = self.cliente.post("/predecir-fotos/", files=[
            ("archivos", ("foto.jpg", foto, "image/jpeg")) for _ in range(3)])
        self.assertEqual(una.status_code, 200)
        self.assertEqual(lote.status_code, 200)
        self.assertTrue(una.json()["rostro_detectado"])
        self.assertEqual(una.json()["nombre"], lote.json()["nombre"])
        self.assertAlmostEqual(una.json()["confianza"], lote.json()["confianza"], places=4)
        self.assertEqual(lote.json()["fotogramas_con_rostro"], 3)

    def test_mayoria_sin_rostro_rechazada(self):
        foto = Path("data/images/ge_01/ge_01_04.jpeg").read_bytes()
        respuesta = self.cliente.post("/predecir-fotos/", files=[
            ("archivos", ("foto.jpg", contenido, "image/jpeg"))
            for contenido in (foto, self.blanco, self.blanco)])
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.json()["identificado"])
        self.assertFalse(respuesta.json()["rostro_detectado"])
        self.assertEqual(respuesta.json()["fotogramas_con_rostro"], 1)

    def test_contrato_invalido(self):
        self.assertEqual(self.cliente.post("/predecir-fotos/", files=[
            ("archivos", ("x.png", self.blanco, "image/png")) for _ in range(6)]).status_code, 422)
        self.assertEqual(self.cliente.post("/predecir-fotos/", files={
            "archivos": ("x.txt", b"hola", "text/plain")}).status_code, 400)
        self.assertEqual(self.cliente.post("/predecir-fotos/").status_code, 422)
        self.assertEqual(self.cliente.post("/predecir-fotos/", files={
            "archivos": ("x.jpg", b"a" * (8 * 1024 * 1024 + 1), "image/jpeg")}).status_code, 413)


if __name__ == "__main__":
    unittest.main(verbosity=2)
