# Guardar y restaurar el trabajo

El código y los modelos ya están guardados en disco. En VS Code, Ctrl+K y luego
S guarda todos los archivos que todavía tengan cambios en el editor.

## Respaldo completo

El ZIP de `respaldos/` contiene el código de la API y la app, los modelos
preentrenados con sus licencias, las galerías y modelos entrenados, los informes,
las fotos disponibles y la cuarentena. Incluye un manifiesto SHA-256 por archivo.
No incluye entornos virtuales, sesiones de Google, secretos OAuth, carpetas Git,
cachés de DVC, dependencias Node ni registros de procesos en ejecución.

El dataset disponible sigue siendo parcial: 88 fotos limpias de 9 personas.
El puntero DVC de integracion referencia el conjunto original de 300 archivos;
el respaldo no afirma haber recuperado ese conjunto completo.

Para generar otro respaldo desde la carpeta principal:

```powershell
.\proyecto-api-vision\venv\Scripts\python.exe guardar_respaldo.py
```

Copia el ZIP y su archivo `.sha256` a un pendrive o a tu almacenamiento de
respaldo. Guardarlo solo en el mismo disco no protege ante una falla de ese disco.
Este proceso no sube archivos a GitHub ni a Drive.

## Restaurar en otra carpeta o equipo

1. Extrae el ZIP; dentro encontrarás `entrega_etapa_3_app`.
2. Instala Python 3.12 de 64 bits. Abre PowerShell en `proyecto-api-vision`.
3. Crea un entorno e instala las dependencias:

```powershell
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

4. Para ejecutar el motor mejorado no necesitas volver a entrenar ni autenticar
   Google: el respaldo ya incluye sus pesos, galería y fotos disponibles.

```powershell
$env:DIRECTORIO_MODELO = (Resolve-Path .\salidas_mejoradas).Path
.\venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8001
```

5. En otra terminal, desde la misma carpeta:

```powershell
.\venv\Scripts\python.exe -m http.server 5173 --bind 127.0.0.1 --directory app-movil/www
```

Abre http://127.0.0.1:5173 y guarda http://127.0.0.1:8001 en los ajustes de la app.

El respaldo excluye `.git`, por lo que la copia restaurada conserva archivos y
procedencia, pero no es un clon Git. Para continuar versionando el dataset,
clona únicamente `integracion` y revisa los datos recuperados antes de actualizar
su puntero DVC. La carpeta de API de esta entrega tampoco es un repositorio Git.
