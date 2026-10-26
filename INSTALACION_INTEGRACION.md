# Instalación y diagnóstico de reconocimiento — integracion

**Versión más reciente:** [reconocimiento mejorado e inicio en puerto 8001](MEJORAS_RECONOCIMIENTO.md).
Se construyó y evaluó el motor YuNet + SFace con aumento de datos a partir de
las 88 fotos limpias. Este motor convive con el piloto MobileNetV2 descrito abajo.

Revisión: 22 de octubre de 2026. Fuente de datos: únicamente
[`trigoduoc/proyecto-dataset-vision`, rama `integracion`](https://github.com/trigoduoc/proyecto-dataset-vision/tree/integracion),
commit revisado `bf2fb2bfd336029eaa2bb1e5eccf61f70fdb5aaf`.

**Actualización tras recibir el ZIP de imágenes:** se recuperaron 90 fotos de
9 personas usando los IDs de integracion; tras apartar dos copias con etiquetas
contradictorias quedan 88 fotos válidas. El ZIP no contiene las otras 28 personas.
Ver [informe de importación y limpieza](proyecto-api-vision/datos_zip_20261022/LEEME.md).
No se actualizó el puntero DVC de 300 archivos con este subconjunto parcial ni
se entrenó un modelo nuevo. Las secciones siguientes conservan el diagnóstico
anterior y los pasos para cuando se disponga del dataset completo.

## Lo que encontré

| Componente | Evidencia e implicación |
|---|---|
| Repositorio remoto | Contiene ingesta, CSV y puntero DVC. No contiene entrenamiento, API ni app. Esos componentes están en la carpeta local hermana `proyecto-api-vision`. Clonar el dataset por sí solo no instala el sistema completo. |
| Personas | `sujetos.csv` de integracion registra **37 personas**, con IDs que incluyen `mf_01/mf_02` y `mg_01/mg_02`. El entrenamiento debe respetar esa correspondencia. |
| Imágenes | `data/images.dvc` declara **300 archivos**, **94.262.690 bytes**, hash `2d8888f63e6d3a481a73cf5cfe8f43ce.dir`. Las imágenes están en Google Drive, no en Git. Los 37 registros y 300 archivos no permiten deducir cuántas fotos tiene realmente cada sujeto. |
| Copia de integracion | No tiene `data/images/` descargado. La auditoría queda en `proyecto-api-vision/auditoria_integracion.json`, con 37 personas y 0 imágenes locales. No es una auditoría del contenido remoto de las fotos. |
| Modelo actual | `salidas/configuracion.json` y `etiquetas.json` todavía contienen **9 personas**. Sus métricas históricas son 90 fotos, accuracy 66,7 %, F1 macro 0,6604. No puede reconocer como clases nuevas las otras 28 personas del CSV. |
| Aumento existente | Ya había flip, rotación, zoom, traslación y brillo en el entrenamiento. Añadir más transformaciones sin descargar los datos y reentrenar no actualiza el modelo que usa la API. |
| Recorte | Antes la app enviaba el cuadrado central reducido a 128×128; el entrenamiento detectaba y recortaba el rostro. Esa diferencia de escala/posición puede perjudicar la cámara real. |
| Detección | Se conserva el detector Haar frontal. El modelo histórico detectó rostro en 74/90 fotos durante la carga. Perfiles, inclinación, poca luz y varios rostros siguen requiriendo revisión; se clasifica el rostro más grande. |
| Desconocidos | El softmax y su umbral separan imperfectamente a conocidos y desconocidos. Bajar el umbral puede aumentar identificaciones equivocadas. Una baja confianza tampoco demuestra que la persona no exista en el dataset. |
| Ingesta y README remotos | La utilidad `ingestar_datos.py` crea IDs `personaNNN` y copia archivos sin validar formato; las instrucciones usan iniciales. El README de integracion contiene pasos para revisar PR que cambian a otras ramas: no son el procedimiento de instalación para este trabajo. |

Se leyó el contenido de todos los archivos versionados de la rama: README, ingesta,
requirements, CSV, configuración DVC y archivos de exclusión. No se inspeccionaron
las fotos remotas porque falta la autenticación local y su descarga.

## Cambios locales preparados

- `auditar_dataset.py`: verifica rama integracion, registra commit y puntero DVC,
  valida CSV, carpetas, archivos legibles y cantidad mínima de fotos únicas.
  Compara los píxeles decodificados para excluir duplicados exactos de la misma
  persona antes de los pliegues; una foto repetida con otra identidad bloquea el entrenamiento.
  No detecta duplicados aproximados o ráfagas casi idénticas.
- `aumento_datos.py`: mismo aumento para CNN propia y MobileNetV2: flip horizontal,
  rotación ±14,4°, zoom 10 %, traslación 6 %, brillo/contraste 15 % y ruido gaussiano
  leve. Mantiene RGB en [0,1]. Las transformaciones aleatorias solo se activan
  al entrenar; no se crean archivos aumentados dentro del dataset.
- `entrenar_cnn.py`: `--repositorio-dataset` toma CSV e imágenes directamente de
  la rama solicitada, bloquea datos incompletos, exporta auditoría/procedencia y
  muestra ejemplos en `muestras_aumento.png`. `--sin-aumento` permite una comparación.
  Se conserva la validación de 5 pliegues y la calibración dejando una identidad fuera.
- `app.py` y app móvil: nuevo `POST /predecir-fotos/` para 1–5 fotos. La cámara envía
  3 JPEG completos de hasta 800 píxeles en el lado mayor; el servidor aplica
  **la misma función de recorte y normalización usada al entrenar**. Continúan
  disponibles los endpoints anteriores de matrices.
- API: comprueba compatibilidad de modelo, etiquetas y configuración; rechaza
  matrices con píxeles inválidos. La interfaz distingue una identificación fallida
  de una afirmación de que alguien no está registrado.
- `requirements-datos.txt`: dependencias DVC/Drive compatibles en el entorno probado.

Los originales y el modelo en `salidas/` permanecen disponibles. Los cambios de
API/app son locales; no se han subido a GitHub. La copia local del dataset está
en integracion y no se crearon ni fusionaron otras ramas.

## 1. Abrir la carpeta de trabajo

En PowerShell:

```powershell
cd C:\Users\gandr\Downloads\entrega_etapa_3_app
git -C .\proyecto-dataset-vision branch --show-current
```

Debe imprimir `integracion`; ya quedó seleccionada en este equipo.

En otra máquina, copia también `proyecto-api-vision` con los cambios de esta
entrega, este manual y `descargar_integracion.ps1`. Para obtener **solo** la rama
del dataset, ejecuta desde la carpeta de trabajo nueva:

```powershell
git clone --single-branch --branch integracion https://github.com/trigoduoc/proyecto-dataset-vision.git proyecto-dataset-vision
```

Si ya tienes una copia, revisa primero que no tenga cambios tuyos. Para actualizarla
desde integracion, sin mezclar ramas:

```powershell
git -C .\proyecto-dataset-vision fetch origin integracion
git -C .\proyecto-dataset-vision switch integracion
git -C .\proyecto-dataset-vision merge --ff-only origin/integracion
```

Si la actualización falla por divergencia, conserva tus cambios y revisa la
historia; no uses reset ni limpieza de archivos para resolverlo automáticamente.

## 2. Instalar Python y dependencias

Usa Python 3.12 de 64 bits y Git. En este equipo ya existe el entorno virtual y
se instalaron las dependencias de datos. Para una instalación nueva:

```powershell
cd .\proyecto-api-vision
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-datos.txt
.\venv\Scripts\python.exe -m pip check
cd ..
```

No necesitas activar el entorno: los comandos llaman al Python del proyecto.
`pip check` debe terminar con `No broken requirements found`.

## 3. Autenticar Google y descargar las imágenes

Desde `entrega_etapa_3_app`:

```powershell
powershell -ExecutionPolicy Bypass -File .\descargar_integracion.ps1 -ConfigurarCredenciales
```

El script comprueba que la rama sea integracion, pide el ID y el secreto OAuth
del profesor (el secreto se escribe oculto), completa un único inicio de sesión
y después ejecuta `dvc pull data/images.dvc --jobs 1` sin autorización interactiva.
Autoriza Google con la cuenta que tiene acceso al Drive del curso. Las credenciales
del cliente quedan en `.dvc/config.local` y la sesión del usuario en
`.dvc/tmp/gdrive-user.json`, ambos excluidos por Git; no los incluyas al compartir la entrega.
La opción de ejecución anterior se aplica solamente a ese proceso de PowerShell.

Para descargas posteriores con las credenciales ya configuradas:

```powershell
powershell -ExecutionPolicy Bypass -File .\descargar_integracion.ps1
```

Si aparece acceso denegado o faltan objetos DVC, comprueba los permisos con el
profesor. Los commits del CSV/puntero no demuestran que todos los objetos se
hayan subido correctamente a Drive.

**Estado comprobado tras corregir las credenciales, 22 de octubre de 2026:**
la autenticación funciona y la sesión quedó guardada con renovación disponible.
La descarga llegó a Drive, pero falla porque no está disponible el manifiesto
`2d8888f63e6d3a481a73cf5cfe8f43ce.dir`, referenciado por `data/images.dvc` de
`integracion` (`bf2fb2b`, confirmado todavía como último commit remoto).
Se consultó el remoto y se comprobó su ausencia tanto en
`files/md5/2d/8888f63e6d3a481a73cf5cfe8f43ce.dir` como en la estructura antigua
`2d/8888f63e6d3a481a73cf5cfe8f43ce.dir`. Esto significa que el manifiesto no está
disponible para esta cuenta en el remoto configurado; debe revisarse su subida
y acceso con quien integró el dataset.

Quien conserve las imágenes y el caché de **esa misma versión de integracion**
debe ejecutar, desde su copia del dataset y con DVC instalado:

```powershell
git switch integracion
dvc push data/images.dvc
```

El push debe completar la subida del manifiesto y las imágenes referenciadas.
Si esa copia tampoco tiene el manifiesto, el integrador necesita recuperar la
versión completa o corregir y versionar el puntero junto con sus objetos DVC.
No se debe recalcular el puntero desde una carpeta incompleta para ocultar el error.
Cuando el remoto esté completo, en este equipo basta repetir:

```powershell
..\proyecto-api-vision\venv\Scripts\python.exe -m dvc pull data/images.dvc --jobs 1
```

Hasta completar esa descarga quedan pendientes la limpieza real del dataset de
integracion, el entrenamiento y sus métricas. Las pruebas de código ya realizadas
no sustituyen esos pasos.

Si aparece `attempt to write a readonly database`, se trata de la base de estado
local de DVC, antes de acceder a las fotos. En este equipo ya quedó configurada
una ubicación escribible en `.dvc/tmp/estado-local` y `dvc status` funciona.
Para aplicar la misma solución manual en otra copia, desde `proyecto-dataset-vision`:

```powershell
$cacheEstadoProyecto = Join-Path (Get-Location) '.dvc\tmp\estado-local'
..\proyecto-api-vision\venv\Scripts\python.exe -m dvc config --local core.site_cache_dir $cacheEstadoProyecto
..\proyecto-api-vision\venv\Scripts\python.exe -m dvc status
..\proyecto-api-vision\venv\Scripts\python.exe -m dvc pull data/images.dvc --jobs 1
```

`not in cache: data/images` significa que las imágenes aún no se descargaron.
Este ajuste solo cambia archivos temporales de estado; conserva las imágenes,
el caché de objetos, el puntero DVC y las credenciales. No requiere eliminar
carpetas ni ejecutar la terminal como administrador. La opción está documentada
como [core.site_cache_dir](https://doc.dvc.org/user-guide/project-structure/configuration#core).

Si Google indica autenticación correcta pero sigue abriendo pestañas, detén la
consola que repite el intento con Ctrl+C. Vuelve a ejecutar el script actualizado
sin `-ConfigurarCredenciales`: reutiliza el ID y secreto ya guardados, comprueba
que la sesión se haya persistido y detiene la descarga con un error si no puede
usarla. Una pestaña de retorno correcta no demuestra por sí sola que el cliente
haya terminado de obtener y guardar la sesión. El aviso inicial de caché inexistente
es normal antes de la primera autenticación.

Para comprobar el estado sin abrir Google ni mostrar secretos:

```powershell
powershell -ExecutionPolicy Bypass -File .\descargar_integracion.ps1 -Diagnostico
```

## 4. Auditar antes de entrenar

```powershell
cd .\proyecto-api-vision
.\venv\Scripts\python.exe auditar_dataset.py --repositorio ..\proyecto-dataset-vision --salida auditoria_integracion.json
```

Continúa cuando no haya errores. Revisa en el JSON cuántas fotos únicas tiene
cada una de las 37 personas. El mínimo técnico de 5 es para poder evaluar y
calibrar; no garantiza un reconocimiento fiable.

El entrenamiento no copiará las 90 fotos antiguas como sustituto de la descarga.
Si faltan sujetos, hay imágenes dañadas o identidades contradictorias, hay que
corregir el dataset de integracion y su versión DVC antes de entrenar.

### Limpieza de duplicados autorizada

Después de descargar, desde `proyecto-api-vision`, puedes revisar el plan y aplicar
la limpieza de copias exactas:

```powershell
.\venv\Scripts\python.exe limpiar_duplicados.py --repositorio ..\proyecto-dataset-vision
.\venv\Scripts\python.exe limpiar_duplicados.py --repositorio ..\proyecto-dataset-vision --aplicar
.\venv\Scripts\python.exe auditar_dataset.py --repositorio ..\proyecto-dataset-vision
```

La limpieza conserva una copia por imagen exacta de cada persona. Mueve las copias
sobrantes a `entrega_etapa_3_app/cuarentena_duplicados/<identificador>/`, fuera del
dataset. Un `manifiesto.json` registra origen, copia conservada, destino y hashes.
Para recuperar una copia, muévela desde su ruta `cuarentena` a su ruta `origen`
del manifiesto, comprobando primero que el origen no exista.

Si una imagen aparece con identidades distintas, se conservan **todas las copias
del grupo** y la auditoría bloquea el entrenamiento hasta corregir su etiqueta.
Las fotos parecidas, las tomas consecutivas, las imágenes ilegibles y las personas
del CSV no se eliminan automáticamente. No se equiparan caras por parecido.

Si se movieron copias, actualiza el puntero de la misma rama antes de entrenar:

```powershell
Push-Location ..\proyecto-dataset-vision
..\proyecto-api-vision\venv\Scripts\python.exe -m dvc add data/images
git diff -- data/images.dvc
Pop-Location
```

La procedencia del entrenamiento registra el commit base, el hash del CSV, el
puntero DVC y si los metadatos tienen cambios locales. Así se puede entrenar con
la limpieza local sin exigir un commit inmediato. Para compartir la limpieza
posteriormente habrá que subir los objetos con DVC y versionar el puntero en
`integracion`; estos comandos no publican nada. Un `dvc pull` antes de actualizar
el puntero puede restaurar las copias de la versión anterior.

Verificación de limpieza: `python -m unittest test_limpieza -v`, con cuatro casos
aprobados: cuarentena recuperable, conservación de conflictos, rechazo de fotos
que cambiaron después de auditar y exclusión de la cuarentena del dataset.

## 5. Entrenar y comparar

Si se permite transfer learning en la evaluación, el primer candidato a medir es
MobileNetV2 ya incluido en el proyecto:

```powershell
.\venv\Scripts\python.exe entrenar_cnn.py --repositorio-dataset ..\proyecto-dataset-vision --arquitectura mobilenet --epocas 25 --salida salidas_integracion
```

Necesita conexión para descargar pesos ImageNet la primera vez. Son 25 épocas
de la cabeza más 15 de ajuste por modelo. El programa entrena **43 modelos** si
se cargan 37 personas: 5 para validación, 37 para calibración y 1 final. Puede
tardar bastante en CPU; no es un único entrenamiento de 25 épocas.

Si la pauta exige CNN propia desde cero:

```powershell
.\venv\Scripts\python.exe entrenar_cnn.py --repositorio-dataset ..\proyecto-dataset-vision --arquitectura propia --epocas 120 --salida salidas_integracion_cnn
```

Para medir el aporte del aumento, repite la arquitectura y épocas elegidas en
otra carpeta. Ejemplo con MobileNetV2:

```powershell
.\venv\Scripts\python.exe entrenar_cnn.py --repositorio-dataset ..\proyecto-dataset-vision --arquitectura mobilenet --epocas 25 --sin-aumento --salida salidas_integracion_control
```

Compara `metricas.json`, F1 macro y por persona, matriz de confusión y rechazo de
desconocidos. Los pliegues usan las mismas semillas. La comparación con y sin
aumento sirve para medir esa variable; la comparación contra el antiguo modelo
de 9 personas no usa las mismas clases y no es una comparación directa de precisión.

Examina `muestras_aumento.png`: las variantes deben conservar rasgos y encuadre
razonables. El aumento se aplica después de separar los originales en pliegues;
la validación no recibe variantes aleatorias. Duplicados aproximados o fotos de
una misma sesión pueden seguir haciendo optimista la validación.

## 6. Iniciar la API con el modelo nuevo

Cuando termine el entrenamiento y existan sus tres artefactos:

```powershell
$env:DIRECTORIO_MODELO = (Resolve-Path .\salidas_integracion).Path
.\venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Para CNN propia, cambia la ruta a `salidas_integracion_cnn`.
En otra terminal, comprueba:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/salud | ConvertTo-Json -Depth 8
```

Comprueba que aparecen las personas entrenadas y `procedencia_dataset.rama =
integracion`. Si muestra 9 personas o procedencia nula, estás sirviendo la salida
antigua. En `http://127.0.0.1:8000/docs` puedes probar `/predecir-fotos/`.

## 7. Probar e instalar la app

Para el navegador del PC puedes servir la app sin Node, en otra terminal:

```powershell
cd C:\Users\gandr\Downloads\entrega_etapa_3_app\proyecto-api-vision
.\venv\Scripts\python.exe -m http.server 5173 --bind 127.0.0.1 --directory app-movil/www
```

Abre `http://localhost:5173`, permite la cámara y configura en Ajustes la API
`http://127.0.0.1:8000`. Prueba conexión antes de identificar.

Para generar APK, instala Node.js 22, JDK 21 y Android Studio con SDK 36 (la
configuración del proyecto usa esos valores). Desde `proyecto-api-vision`:

```powershell
cd .\app-movil
npm ci
npm run probar-matriz
npx cap sync android
cd .\android
.\gradlew.bat assembleDebug
```

El APK queda en `app-movil/android/app/build/outputs/apk/debug/app-debug.apk`.
Transfiérelo al teléfono, permite su instalación y concede permiso de cámara.
Hay que recompilar: el APK anterior seguirá enviando matrices con el recorte viejo.

Para usar la API del PC desde el teléfono, la URL de localhost del teléfono no
apunta al PC. Puedes abrir un túnel HTTPS desde otra terminal, con `cloudflared`
instalado, mientras uvicorn sigue ejecutándose:

```powershell
cloudflared tunnel --url http://localhost:8000
```

Copia la URL HTTPS que imprima a Ajustes de la app. Mantén API y túnel activos.
La compilación Android y el teléfono físico quedan pendientes de comprobar.
Los workflows locales de APK están configurados para `main`, y el remoto de
dataset no contiene la app: no dependen de ellos estos pasos locales.

## Verificación del código y siguiente evaluación

Resultado de esta revisión: **10/10 regresiones aprobadas**, **3/3 recorridos en
Edge aprobados**, `pip check` sin conflictos y sintaxis del script PowerShell
validada. No se entrenó un modelo nuevo ni se compiló un APK.

Desde `proyecto-api-vision`, las regresiones utilizan el modelo histórico y sus
fotos locales como fixtures; no sustituyen el entrenamiento de integracion:

```powershell
.\venv\Scripts\python.exe -m unittest test_mejoras -v
.\venv\Scripts\python.exe -m pip install playwright
.\venv\Scripts\python.exe app-movil/scripts/probar_fotos_e2e.py
```

La prueba de navegador usa Edge sin ventana en Windows. Comprueba transporte de
3 fotos, foto elegida desde archivo, rechazo sin rostro y concordancia entre
respuesta de API y pantalla. Guarda resultados en `pruebas_fotos_e2e/`.
El script anterior `probar_e2e.py` documenta/prueba el flujo antiguo de matrices.

Después de entrenar, reserva una sesión nueva de cámara para **cada persona**,
con otros fondos, ropa, distancia y luz, además de personas ajenas al dataset.
Mide identificaciones correctas, equivocadas y rechazadas, junto con el tiempo
de respuesta. Mantén esas fotos fuera del entrenamiento y de la selección de
parámetros. Si ajustas el umbral con una parte de ellas, usa otra parte aparte
para la evaluación final. Ruido, blanco o degradados solo prueban ausencia de
rostros; no son una prueba de rechazo de personas desconocidas.

Prioridad inmediata: autenticar y descargar DVC, resolver la auditoría, entrenar
con los datos completos y medir en cámara real. Si siguen fallando perfiles o
inclinaciones, habrá que evaluar otro detector y repetir el preprocesamiento;
si confunde identidades incluso con buenos recortes, comparar otro extractor
preentrenado y recoger más sesiones reales.

Referencias: [aumento de datos de TensorFlow](https://www.tensorflow.org/tutorials/images/data_augmentation),
[transfer learning en Keras](https://keras.io/guides/transfer_learning/),
[Google Drive con DVC](https://doc.dvc.org/user-guide/data-management/remote-storage/google-drive).
