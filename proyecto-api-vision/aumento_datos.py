"""Aumento en línea, compartido por ambas CNN y desactivado en inferencia."""
from tensorflow import keras
from tensorflow.keras import layers

CONFIGURACION_AUMENTO = {
    "volteo": "horizontal", "rotacion": 0.04, "zoom": 0.10,
    "traslacion": 0.06, "brillo": 0.15, "contraste": 0.15,
    "rango": [0.0, 1.0], "solo_entrenamiento": True,
    "ruido_gaussiano": 0.015,
}


def construir_aumento():
    c = CONFIGURACION_AUMENTO
    return keras.Sequential([
        layers.RandomFlip(c["volteo"]),
        layers.RandomRotation(c["rotacion"], fill_mode="reflect"),
        layers.RandomZoom(c["zoom"], fill_mode="reflect"),
        layers.RandomTranslation(c["traslacion"], c["traslacion"], fill_mode="reflect"),
        layers.RandomBrightness(c["brillo"], value_range=(0.0, 1.0)),
        layers.RandomContrast(c["contraste"], value_range=(0.0, 1.0)),
        layers.GaussianNoise(c["ruido_gaussiano"]),
        layers.ReLU(max_value=1.0),  # conserva el rango RGB tras agregar ruido
    ], name="aumento_rostros")
