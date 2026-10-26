"""
Entrenamiento de la CNN de reconocimiento de personas (EP2 - Deep Learning).

Etapas que ejecuta este script:
    1. Carga del dataset: imágenes + nombres reales desde `sujetos.csv`.
    2. Preprocesamiento: recorte de rostro y matriz 128x128x3 normalizada.
    3. Evaluación honesta con validación cruzada estratificada (5 pliegues):
       precisión, recall y F1 por persona + matriz de confusión.
    4. Calibración del umbral de "no está en la base de datos" con la técnica
       "dejar una persona fuera": cada persona se trata como desconocida una vez.
    5. Entrenamiento del modelo final con todas las imágenes y guardado de
       artefactos (modelo, etiquetas, configuración, métricas y gráficos).

Uso:
    python entrenar_cnn.py --repositorio-dataset ../proyecto-dataset-vision --salida salidas_integracion
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # sin ventana: genera los gráficos directo a archivo
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tensorflow as tf
from PIL import Image
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from tensorflow import keras
from tensorflow.keras import layers

from preprocesamiento import FORMA_ENTRADA, imagen_a_matriz
from auditar_dataset import auditar, procedencia_repositorio
from aumento_datos import CONFIGURACION_AUMENTO, construir_aumento

SEMILLA = 42
EXTENSIONES_VALIDAS = (".jpg", ".jpeg", ".png")


# ---------------------------------------------------------------------------
# 1 y 2. Carga y preprocesamiento
# ---------------------------------------------------------------------------
def cargar_dataset(ruta_imagenes: Path, ruta_csv: Path):
    """
    Lee `sujetos.csv` (id_carpeta, nombre_normalizado, nombre_original) y carga
    las fotos de cada carpeta. La etiqueta de cada foto es el nombre original.

    Las carpetas que no figuran en el CSV (p. ej. datos de prueba) y los
    archivos vacíos o ilegibles se omiten y se informan por consola.
    """
    informe = auditar(ruta_imagenes, ruta_csv)
    if informe["errores"]:
        raise ValueError("Dataset incompleto o inválido:\n" + "\n".join(informe["errores"]))
    tabla_sujetos = pd.DataFrame(informe["personas"])
    archivos_validos = {a["ruta"] for a in informe["archivos"]}

    matrices, etiquetas, rutas, rostro_detectado = [], [], [], []
    nombres_clases = []

    for _, sujeto in tabla_sujetos.iterrows():
        carpeta = ruta_imagenes / sujeto["id_carpeta"]
        if not carpeta.is_dir():
            print(f"  [aviso] Carpeta inexistente para {sujeto['id_carpeta']}")
            continue

        indice_clase = len(nombres_clases)
        nombres_clases.append(sujeto["nombre_original"])

        for archivo in sorted(carpeta.iterdir()):
            if str(archivo) not in archivos_validos:
                continue
            try:
                with Image.open(archivo) as imagen:
                    matriz, detectado = imagen_a_matriz(imagen)
            except Exception as error:
                raise ValueError(f"No se pudo preprocesar {archivo}: {error}") from error
            matrices.append(matriz)
            etiquetas.append(indice_clase)
            rutas.append(str(archivo))
            rostro_detectado.append(detectado)

    carpetas_ignoradas = sorted(
        carpeta.name for carpeta in ruta_imagenes.iterdir()
        if carpeta.is_dir() and carpeta.name not in set(tabla_sujetos["id_carpeta"])
    )
    if carpetas_ignoradas:
        print(f"  Carpetas fuera de sujetos.csv (ignoradas): {carpetas_ignoradas}")

    return (
        np.asarray(matrices, dtype=np.float32),
        np.asarray(etiquetas, dtype=np.int64),
        nombres_clases,
        rutas,
        np.asarray(rostro_detectado),
    )


# ---------------------------------------------------------------------------
# Modelo: CNN con convolución y pooling
# ---------------------------------------------------------------------------
def construir_cnn(numero_clases: int, con_aumento: bool = True,
                  con_batchnorm: bool = False) -> keras.Model:
    """
    CNN pequeña, adecuada para un dataset de ~10 fotos por persona.

    - Aumento de datos (solo activo al entrenar): volteo, rotación, zoom,
      traslación, brillo y contraste. Compensa la escasez de fotos.
    - 4 bloques Conv2D + MaxPooling: extraen rasgos de bordes a partes del
      rostro y reducen la resolución a la mitad cada vez.
    - GlobalAveragePooling + Dropout: pocos parámetros y menos sobreajuste que
      un Flatten sobre mapas de 8x8x128.
    - BatchNorm DESACTIVADO por defecto. Decisión basada en experimentos con
      ~72 fotos de entrenamiento: con BatchNorm la red memorizaba (accuracy de
      entrenamiento 97-99 %) pero generalizaba peor (validación 22-72 %);
      sin BatchNorm y con entrenamiento largo la validación subió a ~75-81 %.
    """
    capas = [layers.Input(shape=FORMA_ENTRADA)]
    if con_aumento:
        capas.append(construir_aumento())
    for filtros in (16, 32, 64, 128):
        capas.append(layers.Conv2D(filtros, 3, padding="same", activation="relu"))
        if con_batchnorm:
            capas.append(layers.BatchNormalization())
        capas.append(layers.MaxPooling2D())
    capas += [
        layers.GlobalAveragePooling2D(),
        layers.Dropout(0.4),
        layers.Dense(64, activation="relu"),
        layers.Dense(numero_clases, activation="softmax"),
    ]
    return keras.Sequential(capas, name="cnn_rostros")


def construir_mobilenet(numero_clases: int, pesos: str | None = "imagenet", con_aumento=True):
    """
    Alternativa con transfer learning: MobileNetV2 (CNN preentrenada en ImageNet)
    como extractor de rasgos + una cabeza de clasificación propia.

    Requiere internet la primera vez para descargar los pesos (p. ej. en Colab).
    Con `pesos=None` construye la misma arquitectura sin pesos (solo para
    probar el código sin conexión).

    Devuelve (modelo, base) para poder descongelar parte de `base` después.
    """
    base = keras.applications.MobileNetV2(
        input_shape=FORMA_ENTRADA, include_top=False, weights=pesos)
    base.trainable = False  # fase 1: solo se entrena la cabeza

    entradas = keras.Input(shape=FORMA_ENTRADA)
    x = construir_aumento()(entradas) if con_aumento else entradas
    x = layers.Rescaling(2.0, offset=-1.0)(x)  # [0,1] -> [-1,1], lo que espera MobileNetV2
    x = base(x, training=False)
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dropout(0.3)(x)
    salidas = layers.Dense(numero_clases, activation="softmax")(x)
    return keras.Model(entradas, salidas, name="mobilenetv2_rostros"), base


def _compilar(modelo, tasa_aprendizaje):
    modelo.compile(
        optimizer=keras.optimizers.Adam(tasa_aprendizaje),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )


def entrenar_modelo(X_entrenamiento, y_entrenamiento, numero_clases, epocas,
                    datos_validacion=None, semilla=SEMILLA, con_aumento=True,
                    con_batchnorm=False, tamano_lote=8, tasa_aprendizaje=1e-3,
                    arquitectura="propia", pesos="imagenet"):
    """
    Construye, compila y entrena un modelo nuevo. Devuelve (modelo, historial).

    arquitectura:
        "propia"    CNN diseñada en este proyecto, entrenada desde cero.
        "mobilenet" Transfer learning: fase 1 entrena la cabeza (`epocas`
                    épocas) y fase 2 afina las últimas capas de MobileNetV2
                    (15 épocas con tasa de aprendizaje baja).
    """
    keras.utils.set_random_seed(semilla)

    if arquitectura == "propia":
        modelo = construir_cnn(numero_clases, con_aumento, con_batchnorm)
        _compilar(modelo, tasa_aprendizaje)
        historial = modelo.fit(
            X_entrenamiento, y_entrenamiento, validation_data=datos_validacion,
            epochs=epocas, batch_size=tamano_lote, verbose=0)
        return modelo, historial.history

    modelo, base = construir_mobilenet(numero_clases, pesos, con_aumento)
    _compilar(modelo, tasa_aprendizaje)
    fase1 = modelo.fit(
        X_entrenamiento, y_entrenamiento, validation_data=datos_validacion,
        epochs=epocas, batch_size=tamano_lote, verbose=0)

    base.trainable = True
    for capa in base.layers[:-40]:   # solo se afinan las últimas 40 capas
        capa.trainable = False
    _compilar(modelo, 1e-5)
    fase2 = modelo.fit(
        X_entrenamiento, y_entrenamiento, validation_data=datos_validacion,
        epochs=15, batch_size=tamano_lote, verbose=0)

    historial = {clave: fase1.history[clave] + fase2.history[clave]
                 for clave in fase1.history}
    return modelo, historial


# ---------------------------------------------------------------------------
# 3. Validación cruzada estratificada
# ---------------------------------------------------------------------------
def validacion_cruzada(X, y, numero_clases, epocas, pliegues=5, **opciones_modelo):
    """
    Entrena `pliegues` modelos y predice cada imagen con un modelo que NO la vio
    durante el entrenamiento (predicciones "out-of-fold"). Es mucho más estable
    que un único test de 18 imágenes.
    """
    probabilidades = np.zeros((len(y), numero_clases), dtype=np.float32)
    precision_por_pliegue = []
    historial_primer_pliegue = None
    divisor = StratifiedKFold(n_splits=pliegues, shuffle=True, random_state=SEMILLA)

    for numero, (idx_entrenamiento, idx_prueba) in enumerate(divisor.split(X, y), 1):
        inicio = time.perf_counter()
        validacion = (X[idx_prueba], y[idx_prueba]) if numero == 1 else None
        modelo, historial = entrenar_modelo(
            X[idx_entrenamiento], y[idx_entrenamiento], numero_clases, epocas,
            datos_validacion=validacion, semilla=SEMILLA + numero, **opciones_modelo,
        )
        if numero == 1:
            historial_primer_pliegue = historial
        probabilidades[idx_prueba] = modelo.predict(X[idx_prueba], verbose=0)
        exactitud = accuracy_score(y[idx_prueba], probabilidades[idx_prueba].argmax(1))
        precision_por_pliegue.append(exactitud)
        print(f"  pliegue {numero}/{pliegues}: accuracy={exactitud:.3f} "
              f"({time.perf_counter() - inicio:.0f} s)", flush=True)
        keras.backend.clear_session()

    return probabilidades, precision_por_pliegue, historial_primer_pliegue


# ---------------------------------------------------------------------------
# 4. Calibración del umbral de rechazo ("no está en la base de datos")
# ---------------------------------------------------------------------------
def calibrar_umbral(X, y, numero_clases, epocas, **opciones_modelo):
    """
    Técnica "dejar una persona fuera": para cada persona P se entrena con las
    otras personas y se observa cuánta confianza muestra el modelo ante:
        - fotos nuevas de personas CONOCIDAS (deberían aceptarse), y
        - fotos de P, a quien el modelo nunca vio (deberían rechazarse).
    Con esas confianzas se elige el umbral que mejor separa ambos casos.
    """
    confianza_conocidos, acierto_conocidos, confianza_desconocidos = [], [], []

    for persona in range(numero_clases):
        inicio = time.perf_counter()
        es_desconocida = y == persona
        indices_conocidos = np.where(~es_desconocida)[0]

        # Reetiquetado 0..K-2 para las personas conocidas
        clases_conocidas = [c for c in range(numero_clases) if c != persona]
        reetiquetado = {c: i for i, c in enumerate(clases_conocidas)}
        y_conocidos = np.array([reetiquetado[c] for c in y[indices_conocidos]])

        idx_ent, idx_prueba = train_test_split(
            np.arange(len(indices_conocidos)), test_size=0.2,
            random_state=SEMILLA, stratify=y_conocidos,
        )
        X_conocidos = X[indices_conocidos]
        modelo, _ = entrenar_modelo(
            X_conocidos[idx_ent], y_conocidos[idx_ent], numero_clases - 1, epocas,
            semilla=SEMILLA + 100 + persona, **opciones_modelo,
        )
        prob_conocidos = modelo.predict(X_conocidos[idx_prueba], verbose=0)
        prob_desconocidos = modelo.predict(X[es_desconocida], verbose=0)

        confianza_conocidos += prob_conocidos.max(1).tolist()
        acierto_conocidos += (prob_conocidos.argmax(1) == y_conocidos[idx_prueba]).tolist()
        confianza_desconocidos += prob_desconocidos.max(1).tolist()
        print(f"  persona fuera {persona + 1}/{numero_clases} "
              f"({time.perf_counter() - inicio:.0f} s)", flush=True)
        keras.backend.clear_session()

    confianza_conocidos = np.array(confianza_conocidos)
    acierto_conocidos = np.array(acierto_conocidos)
    confianza_desconocidos = np.array(confianza_desconocidos)

    umbrales = np.linspace(0.30, 0.99, 140)
    # Conocido "bien atendido": acertó Y superó el umbral. Desconocido "bien
    # rechazado": su confianza quedó bajo el umbral.
    tasa_conocidos_ok = np.array(
        [np.mean(acierto_conocidos & (confianza_conocidos >= u)) for u in umbrales]
    )
    tasa_rechazo_desconocidos = np.array(
        [np.mean(confianza_desconocidos < u) for u in umbrales]
    )
    puntaje = (tasa_conocidos_ok + tasa_rechazo_desconocidos) / 2
    mejor = int(np.argmax(puntaje))

    return {
        "umbral": float(umbrales[mejor]),
        "tasa_conocidos_aceptados_correctos": float(tasa_conocidos_ok[mejor]),
        "tasa_desconocidos_rechazados": float(tasa_rechazo_desconocidos[mejor]),
        "puntaje_balanceado": float(puntaje[mejor]),
        "umbrales": umbrales,
        "curva_conocidos": tasa_conocidos_ok,
        "curva_rechazo": tasa_rechazo_desconocidos,
        "confianza_conocidos": confianza_conocidos,
        "confianza_desconocidos": confianza_desconocidos,
    }


# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------
def graficar_matriz_confusion(matriz, nombres, ruta):
    figura, eje = plt.subplots(figsize=(8.5, 7))
    imagen = eje.imshow(matriz, cmap="Blues")
    eje.set_xticks(range(len(nombres)), nombres, rotation=45, ha="right")
    eje.set_yticks(range(len(nombres)), nombres)
    eje.set_xlabel("Predicción")
    eje.set_ylabel("Persona real")
    eje.set_title("Matriz de confusión (validación cruzada, 5 pliegues)")
    for i in range(len(nombres)):
        for j in range(len(nombres)):
            eje.text(j, i, matriz[i, j], ha="center", va="center",
                     color="white" if matriz[i, j] > matriz.max() / 2 else "black")
    figura.colorbar(imagen)
    figura.tight_layout()
    figura.savefig(ruta, dpi=150)
    plt.close(figura)


def graficar_curvas(historial, ruta):
    epocas = np.arange(1, len(historial["loss"]) + 1)
    figura, ejes = plt.subplots(1, 2, figsize=(11, 4))
    for eje, metrica, titulo in zip(ejes, ["accuracy", "loss"], ["Accuracy", "Pérdida"]):
        eje.plot(epocas, historial[metrica], label="Entrenamiento")
        eje.plot(epocas, historial[f"val_{metrica}"], label="Validación (pliegue 1)")
        eje.set_title(f"{titulo} por época")
        eje.set_xlabel("Época")
        eje.grid(alpha=0.25)
        eje.legend()
    figura.tight_layout()
    figura.savefig(ruta, dpi=150)
    plt.close(figura)


def graficar_aumento(X, y, nombres, ruta):
    """Vista previa, sin guardar copias aumentadas dentro del dataset."""
    keras.utils.set_random_seed(SEMILLA)
    aumento = construir_aumento()
    clases = np.unique(y)[:6]
    figura, ejes = plt.subplots(len(clases), 4, figsize=(9, 2.5 * len(clases)), squeeze=False)
    for fila, clase in enumerate(clases):
        original = X[np.flatnonzero(y == clase)[0]]
        variantes = aumento(np.repeat(original[None], 3, axis=0), training=True).numpy()
        for columna, imagen in enumerate([original, *variantes]):
            ejes[fila, columna].imshow(imagen)
            ejes[fila, columna].axis("off")
            ejes[fila, columna].set_title(nombres[clase] if columna == 0 else f"Variante {columna}")
    figura.tight_layout()
    figura.savefig(ruta, dpi=120)
    plt.close(figura)


def graficar_umbral(calibracion, ruta):
    figura, ejes = plt.subplots(1, 2, figsize=(11, 4))
    ejes[0].hist(calibracion["confianza_conocidos"], bins=15, alpha=0.7,
                 label="Personas conocidas")
    ejes[0].hist(calibracion["confianza_desconocidos"], bins=15, alpha=0.7,
                 label="Personas desconocidas")
    ejes[0].axvline(calibracion["umbral"], color="k", linestyle="--",
                    label=f"Umbral = {calibracion['umbral']:.2f}")
    ejes[0].set_title("Confianza del modelo")
    ejes[0].set_xlabel("Probabilidad máxima")
    ejes[0].legend()

    ejes[1].plot(calibracion["umbrales"], calibracion["curva_conocidos"],
                 label="Conocidos aceptados y correctos")
    ejes[1].plot(calibracion["umbrales"], calibracion["curva_rechazo"],
                 label="Desconocidos rechazados")
    ejes[1].axvline(calibracion["umbral"], color="k", linestyle="--")
    ejes[1].set_title("Elección del umbral")
    ejes[1].set_xlabel("Umbral de confianza")
    ejes[1].grid(alpha=0.25)
    ejes[1].legend()
    figura.tight_layout()
    figura.savefig(ruta, dpi=150)
    plt.close(figura)


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------
def principal():
    analizador = argparse.ArgumentParser(description=__doc__,
                                         formatter_class=argparse.RawTextHelpFormatter)
    analizador.add_argument("--imagenes", type=Path, default=Path("data/images"))
    analizador.add_argument("--csv", type=Path, default=Path("sujetos.csv"))
    analizador.add_argument("--salida", type=Path, default=Path("salidas"))
    analizador.add_argument("--repositorio-dataset", type=Path,
                            help="Lee CSV e imágenes directamente de esta copia; exige integracion.")
    analizador.add_argument("--sin-aumento", action="store_true",
                            help="Control experimental: entrena sin transformaciones aleatorias.")
    analizador.add_argument("--epocas", type=int, default=120,
                            help="Épocas (en 'mobilenet' son las de la fase 1; sugerido: 25).")
    analizador.add_argument("--arquitectura", choices=["propia", "mobilenet"],
                            default="propia",
                            help="'propia': CNN desde cero. 'mobilenet': transfer learning "
                                 "(requiere internet para bajar los pesos).")
    args = analizador.parse_args()
    if args.epocas < 1:
        analizador.error("--epocas debe ser positivo")
    procedencia = None
    if args.repositorio_dataset:
        procedencia = procedencia_repositorio(args.repositorio_dataset)
        args.imagenes = args.repositorio_dataset / "data/images"
        args.csv = args.repositorio_dataset / "sujetos.csv"
    opciones_modelo = {"arquitectura": args.arquitectura, "con_aumento": not args.sin_aumento}
    args.salida.mkdir(parents=True, exist_ok=True)

    informe = auditar(args.imagenes, args.csv)
    informe["procedencia"] = procedencia
    (args.salida / "auditoria_dataset.json").write_text(
        json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    if informe["errores"]:
        raise ValueError("No se entrenará con datos incompletos:\n" + "\n".join(informe["errores"]))

    print("1) Cargando dataset...", flush=True)
    X, y, nombres, rutas, rostro_detectado = cargar_dataset(args.imagenes, args.csv)
    numero_clases = len(nombres)
    if not args.sin_aumento:
        graficar_aumento(X, y, nombres, args.salida / "muestras_aumento.png")
    print(f"  {len(y)} imágenes, {numero_clases} personas, forma={X.shape[1:]}, "
          f"rostro detectado en {rostro_detectado.sum()}/{len(y)} "
          f"(resto: recorte central de respaldo)")

    print("2) Validación cruzada (5 pliegues)...", flush=True)
    probabilidades, exactitudes, historial = validacion_cruzada(
        X, y, numero_clases, args.epocas, **opciones_modelo)
    y_predicho = probabilidades.argmax(1)

    precision, recall, f1, soporte = precision_recall_fscore_support(
        y, y_predicho, labels=range(numero_clases), zero_division=0)
    macro = precision_recall_fscore_support(
        y, y_predicho, average="macro", zero_division=0)[:3]
    reporte_texto = classification_report(
        y, y_predicho, labels=range(numero_clases), target_names=nombres, zero_division=0)
    print(reporte_texto)
    matriz = confusion_matrix(y, y_predicho, labels=range(numero_clases))
    graficar_matriz_confusion(matriz, nombres, args.salida / "matriz_confusion.png")
    graficar_curvas(historial, args.salida / "curvas_entrenamiento.png")

    print("3) Calibrando umbral de desconocidos (una persona fuera a la vez)...", flush=True)
    calibracion = calibrar_umbral(X, y, numero_clases, args.epocas, **opciones_modelo)
    graficar_umbral(calibracion, args.salida / "umbral_desconocidos.png")
    print(f"  Umbral elegido: {calibracion['umbral']:.2f} | conocidos aceptados y "
          f"correctos: {calibracion['tasa_conocidos_aceptados_correctos']:.1%} | "
          f"desconocidos rechazados: {calibracion['tasa_desconocidos_rechazados']:.1%}")

    print("4) Entrenando modelo final con todas las imágenes...", flush=True)
    modelo_final, _ = entrenar_modelo(X, y, numero_clases, args.epocas, **opciones_modelo)
    modelo_final.save(args.salida / "modelo_rostros.keras")

    etiquetas = {str(i): nombre for i, nombre in enumerate(nombres)}
    (args.salida / "etiquetas.json").write_text(
        json.dumps(etiquetas, ensure_ascii=False, indent=2), encoding="utf-8")
    configuracion = {
        "forma_entrada": list(FORMA_ENTRADA),
        "umbral_confianza": calibracion["umbral"],
        "numero_clases": numero_clases,
        "epocas": args.epocas,
        "arquitectura": args.arquitectura,
        "aumento_datos": CONFIGURACION_AUMENTO if not args.sin_aumento else None,
        "procedencia_dataset": procedencia,
    }
    (args.salida / "configuracion.json").write_text(
        json.dumps(configuracion, indent=2), encoding="utf-8")

    metricas = {
        "imagenes": int(len(y)),
        "personas": numero_clases,
        "rostro_detectado": int(rostro_detectado.sum()),
        "validacion_cruzada": {
            "accuracy_global": float(accuracy_score(y, y_predicho)),
            "accuracy_por_pliegue": [float(v) for v in exactitudes],
            "accuracy_media": float(np.mean(exactitudes)),
            "accuracy_desviacion": float(np.std(exactitudes)),
            "precision_macro": float(macro[0]),
            "recall_macro": float(macro[1]),
            "f1_macro": float(macro[2]),
            "por_persona": {
                nombre: {"precision": float(precision[i]), "recall": float(recall[i]),
                         "f1": float(f1[i]), "imagenes": int(soporte[i])}
                for i, nombre in enumerate(nombres)
            },
        },
        "rechazo_desconocidos": {
            "umbral": calibracion["umbral"],
            "conocidos_aceptados_correctos": calibracion["tasa_conocidos_aceptados_correctos"],
            "desconocidos_rechazados": calibracion["tasa_desconocidos_rechazados"],
            "puntaje_balanceado": calibracion["puntaje_balanceado"],
        },
    }
    (args.salida / "metricas.json").write_text(
        json.dumps(metricas, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.salida / "reporte_clasificacion.txt").write_text(reporte_texto, encoding="utf-8")
    print(f"Listo. Artefactos guardados en: {args.salida.resolve()}")


if __name__ == "__main__":
    principal()
