import csv
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from auditar_dataset import auditar
from limpiar_duplicados import aplicar, planificar


class LimpiezaTests(unittest.TestCase):
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
                identificador = f"p{persona}"
                escritor.writerow([identificador, identificador, identificador])
                carpeta = self.imagenes / identificador
                carpeta.mkdir(parents=True)
                for n in range(5):
                    Image.new("RGB", (8, 8), (persona * 70, n * 40, 10)).save(carpeta / f"{n}.png")
        self.original = self.imagenes / "p0/0.png"
        self.copia = self.imagenes / "p0/copia.png"
        self.copia.write_bytes(self.original.read_bytes())

    def plan(self):
        return planificar(auditar(self.imagenes, self.csv))

    def test_simulacion_y_limpieza_recuperable(self):
        plan = self.plan()
        self.assertEqual(len(plan), 1)
        self.assertTrue(self.copia.exists())
        datos = self.copia.read_bytes()
        destino = self.raiz / "cuarentena"
        aplicar(plan, self.imagenes, destino)
        self.assertFalse(self.copia.exists())
        self.assertEqual((destino / "p0/copia.png").read_bytes(), datos)
        self.assertEqual(self.original.read_bytes(), datos)
        registro = json.loads((destino / "manifiesto.json").read_text(encoding="utf-8"))
        self.assertTrue(registro["movimientos"][0]["movido"])
        self.assertEqual(self.plan(), [])
        self.assertFalse(auditar(self.imagenes, self.csv)["errores"])

    def test_conflicto_identidad_conserva_todas_las_copias(self):
        (self.imagenes / "p1/conflicto.png").write_bytes(self.original.read_bytes())
        self.assertEqual(self.plan(), [])
        self.assertTrue(self.copia.exists())

    def test_no_mueve_si_los_pixeles_cambiaron(self):
        plan = self.plan()
        Image.new("RGB", (8, 8), "white").save(self.copia)
        with self.assertRaisesRegex(ValueError, "ya no son idénticas"):
            aplicar(plan, self.imagenes, self.raiz / "cuarentena")
        self.assertTrue(self.copia.exists())

    def test_cuarentena_fuera_del_dataset(self):
        with self.assertRaisesRegex(ValueError, "separada"):
            aplicar(self.plan(), self.imagenes, self.imagenes / "cuarentena")
        self.assertTrue(self.copia.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
