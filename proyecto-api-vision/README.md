# Reconocimiento de personas con CNN — EP2 Deep Learning (AVY1103)

Para probar el nuevo motor de rostros YuNet + SFace, ver
[MEJORAS_RECONOCIMIENTO.md](../MEJORAS_RECONOCIMIENTO.md). Artefactos en
`salidas_mejoradas/`, API local en puerto 8001. Los resultados históricos y el
piloto Keras de las secciones siguientes corresponden a las versiones anteriores.

Actualización para `integracion`: ver [instalación y diagnóstico](../INSTALACION_INTEGRACION.md).
El modelo existente en `salidas/` sigue siendo el de 9 personas. El código actualizado
audita el dataset completo, comparte aumento entre las dos arquitecturas y permite
enviar fotos a `/predecir-fotos/` para aplicar el mismo recorte que en entrenamiento.
Los resultados de abajo son históricos; aún no hay métricas del dataset de `integracion`.

Sistema que identifica a una persona de Duoc UC a partir de una foto de su rostro
y responde su **nombre** o indica que **no está en la base de datos**.

```
App móvil ──(matriz 128x128x3)──▶ API FastAPI ──▶ CNN (Keras) ──▶ nombre | "no está en la base"
```

## Estructura del proyecto

| Archivo | Rol |
|---|---|
| `preprocesamiento.py` | Recorte de rostro, matriz 128×128×3 en [0,1], compuerta de detección de rostro. Lo usan el entrenamiento **y** la API. |
| `entrenar_cnn.py` | Carga de datos, CNN, validación cruzada, calibración del umbral y guardado del modelo. |
| `app.py` | API FastAPI (`/predecir-lote/`, `/predecir-matriz/`, `/predecir/`, `/salud`). |
| `probar_api.py` | Prueba automática de la API con el modelo entrenado. |
| `app-movil/` | App Android (Capacitor) que consume la API. Ver `app-movil/README.md`. |
| `Dockerfile`, `requirements-api.txt` | Imagen mínima para desplegar solo la API (sin probar, ver app-movil/README.md). |
| `salidas/` | Modelo `.keras`, `etiquetas.json`, `configuracion.json`, métricas y gráficos. |

## Etapas del programa

1. **Datos.** `sujetos.csv` asocia cada carpeta (`nc_01`, …) con el nombre real. Se omiten carpetas fuera del CSV y archivos vacíos.
2. **Preprocesamiento.** Corrección de orientación → recorte cuadrado centrado en el rostro (detector Haar, margen 35 %) → redimensión a **128×128** → `float32` en [0, 1]. Si no se detecta rostro (perfil, cabeza inclinada) se usa un recorte central de respaldo.
3. **Modelo (CNN).** Aumento de datos (volteo, rotación, zoom, traslación, brillo, contraste) → 4 bloques `Conv2D(16→32→64→128, 3×3, ReLU)` + `MaxPooling2D` → `GlobalAveragePooling2D` → `Dropout(0.4)` → `Dense(64)` → `Dense(9, softmax)`. Pérdida: entropía cruzada categórica dispersa; optimizador Adam (1e-3); 120 épocas; lote de 8.
4. **Evaluación.** Validación cruzada estratificada de 5 pliegues (cada foto se predice con un modelo que no la vio): precisión, recall, F1 y matriz de confusión.
5. **Rechazo de desconocidos.** (a) Compuerta de rostro: si la imagen no contiene un rostro frontal, se responde "no está en la base de datos". (b) Umbral de confianza calibrado "dejando una persona fuera" (cada persona actúa como desconocida una vez).
6. **API.** Carga el modelo al iniciar y responde JSON.

## Resultados (modelo entrenado desde cero, 90 fotos, 9 personas)

| Métrica (validación cruzada, 5 pliegues) | Valor |
|---|---|
| Accuracy global | **66,7 %** (pliegues: 66,7 / 66,7 / 50,0 / 61,1 / 88,9 %) |
| Precisión / Recall / F1 (macro) | 0,67 / 0,67 / 0,66 |
| Mejor persona (F1) | Gustavo Espinoza 0,95 |
| Peor persona (F1) | Nicolas Cuevas 0,42 |
| Umbral de confianza | 0,77 |
| Conocidos aceptados y correctos | 59,0 % |
| Desconocidos rechazados por umbral | 67,8 % |
| Compuerta de rostro | acepta 81 % de rostros reales; rechaza 100 % de ruido, blanco y degradado |

Detalle por persona: `salidas/reporte_clasificacion.txt` · gráficos: `salidas/*.png`.

### Limitaciones (importante para la presentación)

- **Con ~10 fotos por persona una CNN desde cero rinde moderadamente.** Los resultados son una estimación honesta con validación cruzada, no un test de 18 imágenes.
- **Cada persona tiene un fondo y ropa muy constantes** en sus fotos. El recorte de rostro reduce ese atajo, pero no lo elimina; en el uso real con otros fondos puede rendir menos.
- **El umbral de confianza separa de forma imperfecta** conocidos y desconocidos (ver `salidas/umbral_desconocidos.png`).
- La compuerta de rostro exige una cara **frontal y clara**: perfiles o caras muy inclinadas se rechazan.
- Agregar las fotos del resto del curso (más personas y más variedad) es la mejora que más impacto tiene.

### Mejora recomendada: transfer learning

`entrenar_cnn.py --arquitectura mobilenet --epocas 25` entrena una **MobileNetV2 preentrenada en ImageNet** (CNN con convolución y pooling) con una cabeza propia. Necesita internet para descargar los pesos, por eso debe ejecutarse en Google Colab o en un PC con conexión. Genera los mismos artefactos y es compatible con la API sin cambios.

## Uso

Requiere **Python 3.10–3.13** (TensorFlow aún no soporta 3.14).

```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Entrenar (genera la carpeta salidas/)
python entrenar_cnn.py --imagenes data/images --csv sujetos.csv --salida salidas

# Probar la API sin servidor
python probar_api.py

# Levantar la API
uvicorn app:app --host 0.0.0.0 --port 8000
```

Documentación interactiva: `http://127.0.0.1:8000/docs`.

## Contrato de la API

**`POST /predecir-lote/`** — lo que usa la app: de 1 a 5 matrices de la misma persona

```json
{ "matrices": [ <matriz 128x128x3>, <matriz 128x128x3>, <matriz 128x128x3> ], "normalizada": false }
```
Exige rostro en al menos la mitad de las matrices y **promedia** las probabilidades de las que lo tienen.

**`POST /predecir-matriz/`** — una sola matriz

```json
{ "matriz": [[[R, G, B], ...128 columnas...], ...128 filas...], "normalizada": false }
```
`normalizada=false` → valores 0–255 (por defecto); `true` → valores 0–1.

**`POST /predecir/`** — foto completa (`multipart/form-data`, campo `archivo`); recorta el rostro en el servidor.

**Respuesta (ambos):**

```json
{
  "rostro_detectado": true,
  "identificado": true,
  "nombre": "Gustavo Espinoza",
  "confianza": 0.9996,
  "umbral": 0.7666,
  "mensaje": "Persona identificada: Gustavo Espinoza",
  "candidatos": [{"nombre": "Gustavo Espinoza", "probabilidad": 0.9996}],
  "fotogramas_analizados": 3,
  "fotogramas_con_rostro": 3
}
```
Si no hay rostro o la confianza no supera el umbral: `identificado=false`, `nombre=null` y el mensaje *"La persona no está en la base de datos…"*.

Errores: `400` archivo que no es imagen · `422` matriz con forma distinta de 128×128×3.

## App móvil

La app (carpeta `app-movil/`) muestra una **guía ovalada** (el modelo se entrenó con recortes donde el rostro ocupa ~60 % del ancho), recorta el cuadrado central, lo reduce a 128×128, captura 3 fotogramas y los envía a `/predecir-lote/`. Instrucciones para generar el APK en `app-movil/README.md`.

## Estado de las pruebas

| Componente | Prueba | Resultado |
|---|---|---|
| API | `python probar_api.py` | Aprobada (nombres, rechazo de no-rostros, validaciones) |
| Conversión a matriz (app) | `npm run probar-matriz` | 7/7 |
| App + API de punta a punta | `python app-movil/scripts/probar_e2e.py` | 4/5 (el fallo es del modelo, no de la app) |
| APK en teléfono real | — | **No verificado** |

## Referencias

- Chollet, F. (2021). *Deep Learning with Python* (2.ª ed.). Manning.
- Sandler, M., Howard, A., Zhu, M., Zhmoginov, A., & Chen, L.-C. (2018). MobileNetV2: Inverted residuals and linear bottlenecks. *CVPR*.
- Viola, P., & Jones, M. (2001). Rapid object detection using a boosted cascade of simple features. *CVPR*.
- Tiangolo, S. (s. f.). *FastAPI documentation*. https://fastapi.tiangolo.com
