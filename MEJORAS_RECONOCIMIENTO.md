# Reconocimiento mejorado, 22 de octubre de 2026

El motor mejorado ya está preparado en `proyecto-api-vision/salidas_mejoradas`.
Utiliza las 88 fotos limpias de 9 personas del ZIP, con los IDs del CSV de
integracion. No incorpora las 28 personas cuyas imágenes siguen faltando.
La rama del dataset, el CSV completo, el puntero DVC de 300 archivos y los
modelos anteriores se conservan.

## Probar ahora

La API mejorada se inició en **http://127.0.0.1:8001**. La anterior puede seguir
corriendo en el 8000 para comparar. En la página **http://127.0.0.1:5173**, pulsa
**Ctrl+F5**, abre Ajustes y guarda `http://127.0.0.1:8001` como URL de la API.
La comprobación de salud debe mostrar `motor: sface` y 9 personas:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/salud
```

## Iniciar de nuevo en otra sesión

En una terminal PowerShell, para la API:

```powershell
cd C:\Users\gandr\Downloads\entrega_etapa_3_app\proyecto-api-vision
$env:DIRECTORIO_MODELO = (Resolve-Path .\salidas_mejoradas).Path
.\venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8001
```

En otra terminal, para la página:

```powershell
cd C:\Users\gandr\Downloads\entrega_etapa_3_app\proyecto-api-vision
.\venv\Scripts\python.exe -m http.server 5173 --bind 127.0.0.1 --directory app-movil/www
```

Si el puerto ya está ocupado por la instancia activa, conserva esa instancia o
detén su terminal antes de volver a iniciarla. La instancia iniciada en segundo
plano guarda registros y su PID en `registros_api_mejorada/`. Para detenerla:

```powershell
$pidGuardado = [int](Get-Content .\registros_api_mejorada\proceso.pid)
Get-Process -Id $pidGuardado | Select-Object Id, ProcessName, StartTime
```

Comprueba que corresponde a la instancia Python iniciada para esta API antes
de ejecutar `Stop-Process -Id $pidGuardado`; el PID puede reutilizarse tras reiniciar.

## Qué cambió

- **YuNet** detecta el rostro y cinco puntos faciales. Se alinean ojos, nariz y
  boca antes de extraer rasgos; se reduce la influencia de fondo y encuadre.
- **SFace** es una CNN preentrenada para comparar rostros, usada como extractor
  de vectores de 128 componentes. La galería se construye con las personas del
  dataset local, sin volver a entrenar millones de parámetros con 88 fotos.
- Hay ocho variantes por original: original, dos cambios de gamma, contraste,
  desenfoque suave, compresión JPEG y dos rotaciones. Se combina cada descriptor
  con su versión en espejo. La galería tiene 696 vectores de 87 rostros detectados.
- Las variantes de una foto permanecen en el mismo grupo durante la evaluación.
  Una foto de validación y todas sus variantes se excluyen juntas de la galería.
  Cada original pesa una sola vez al combinar las similitudes, aunque tenga variantes.
- El umbral y el margen entre los dos primeros candidatos se calibran únicamente
  con el conjunto de entrenamiento de cada pliegue. Los desconocidos simulados
  se construyen retirando todas las fotos de una identidad.
- La API exige similitud suficiente, margen suficiente respecto del segundo
  candidato y consenso de al menos dos tercios de los fotogramas con rostro.
  Un lote de varias fotos necesita al menos dos con rostro. Varios rostros grandes
  en una imagen se rechazan para evitar mezclar identidades.
- La interfaz distingue puntuación de similitud de probabilidad. Los porcentajes
  del modelo anterior y del nuevo tienen significados distintos y no se comparan
  directamente. El nuevo umbral ronda 0,509 y exige margen de 0,15; no se bajó
  el umbral del clasificador anterior para aceptar la captura del usuario.
- Guardar URL ahora comprueba que responde una API válida. Un servidor estático
  produce un mensaje de conexión útil en lugar de dejar solo «Error 501».
- La API anterior Keras y sus endpoints de matrices siguen disponibles. Los
  modelos ONNX se comparten con entrenamiento e inferencia, y su acceso se protege
  para evitar carreras al atender solicitudes concurrentes.

## Resultados y límites

| Medición en las mismas 88 fotos | Piloto MobileNetV2 | YuNet + SFace |
|---|---:|---:|
| Rostros detectados | 72/88 | 87/88 |
| Acierto, cinco pliegues estratificados | 83,0 % | 98,9 % |

En la evaluación del nuevo motor, 86/88 fotos conocidas se aceptaron con identidad
correcta y ninguna foto conocida se aceptó con identidad equivocada. Al retirar
la identidad completa, se rechazó 87/88 fotos como desconocidas. Estos valores
son estimaciones del ZIP, con pocas personas y fotos posiblemente de las mismas
sesiones. **No prueban ese rendimiento en una webcam real ni ante desconocidos
externos.** Las variantes no cuentan como fotos independientes. Queda un fallo
de detección registrado en `salidas_mejoradas/metricas.json`.

Se aprobaron seis pruebas del motor nuevo, catorce regresiones de auditoría,
limpieza y API anterior, tres recorridos con cámara simulada y una prueba del
guardado de la conexión. El Dockerfile admite los artefactos nuevos, pero no se
compiló ni desplegó una imagen Docker en esta revisión.

La próxima prueba debe incluir sesiones de cámara nuevas de todas las personas
y desconocidos externos, registrando aciertos, rechazos, errores y latencia.
No debe usarse una captura conocida para ajustar el umbral y luego reportarla
como una prueba independiente.

## Reproducir

Desde `proyecto-api-vision`:

```powershell
.\venv\Scripts\python.exe descargar_modelos_rostro.py
.\venv\Scripts\python.exe entrenar_rostros.py
.\venv\Scripts\python.exe -m unittest test_motor_rostros -v
```

Los pesos se descargan exclusivamente de OpenCV Zoo. El script contrasta tamaño
y SHA-256 con los punteros Git LFS oficiales. Conserva hashes, URL y licencias en
`modelos_rostro/`, y copia esa procedencia al directorio de resultados. La
auditoría registra la huella de cada imagen utilizada. Para Docker, el valor
predeterminado de `ARTEFACTOS` es `salidas_mejoradas`; puede elegirse una salida
Keras con `--build-arg ARTEFACTOS=salidas_piloto_zip`.

Referencias: [tutorial oficial de OpenCV](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html),
[YuNet y SFace en OpenCV Zoo](https://github.com/opencv/opencv_zoo).
