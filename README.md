# app_deeplearning

Proyecto académico de reconocimiento facial: aplicación web/Android, API FastAPI,
modelos preentrenados, galería facial, código de entrenamiento, datos locales e informes.

La versión mejorada usa YuNet para detectar y alinear el rostro y SFace para
obtener descriptores de 128 componentes. Compara con la galería y exige similitud,
margen entre candidatos y consenso entre fotogramas antes de identificar.

## Contenido

- `proyecto-api-vision/`: API, entrenamiento, pruebas, modelos e informes.
- `proyecto-api-vision/app-movil/`: interfaz HTML/CSS/JavaScript y proyecto Android Capacitor.
- `proyecto-dataset-vision/`: CSV, referencia DVC y las 88 fotos limpias disponibles.
- `dataset_pr5/`: datos originales locales anteriores a la limpieza.
- `cuarentena_duplicados/`: imágenes apartadas y manifiestos de recuperación.
- `MANIFIESTO_EXPORTACION.json`: tamaños y SHA-256 de los archivos copiados de la entrega.

Esta es una copia independiente de los archivos, sin el historial Git del dataset
original. No incluye entornos virtuales, node_modules, cachés, credenciales ni ZIP
de respaldo; las dependencias se reinstalan a partir de los archivos del proyecto.

## Datos y resultados

La galería mejorada utiliza **88 fotos limpias de 9 personas**; YuNet detectó 87
rostros y se generaron 696 vectores con ocho variantes por rostro. El CSV completo
contiene 37 personas y el puntero DVC referencia 300 archivos: **faltan las imágenes
de otras 28 personas**. Las fotos locales no reemplazan esa versión completa.

El acierto registrado de validación cruzada es 98,9 % y 86/88 fotos conocidas se
aceptaron con identidad correcta. Son resultados del subconjunto disponible;
queda pendiente evaluar sesiones nuevas de cámara y desconocidos externos.
La prueba de cámara física en Android y el despliegue Docker no están verificados.

Por contener fotos, nombres y descriptores faciales, la publicación preparada usa
un repositorio privado. Las licencias de YuNet y SFace están en
`proyecto-api-vision/modelos_rostro/`; se conserva también su procedencia.

## Ejecutar en Windows

Requisito: Python 3.12 de 64 bits. Desde la raíz del repositorio, en PowerShell:

```powershell
cd .\proyecto-api-vision
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DIRECTORIO_MODELO = "$PWD\salidas_mejoradas"
.\venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8001
```

En otra terminal, desde la raíz del repositorio:

```powershell
cd .\proyecto-api-vision
.\venv\Scripts\python.exe -m http.server 5173 --bind 127.0.0.1 --directory app-movil/www
```

Abre http://localhost:5173, permite la cámara y configura en Ajustes la API
`http://127.0.0.1:8001`. La comprobación http://127.0.0.1:8001/salud debe indicar
`motor: sface` y 9 personas. Se puede usar la galería incluida sin entrenar otra vez
ni autenticar Google. Mantén ambas terminales abiertas; Ctrl+C detiene cada servidor.

## Subir a GitHub desde PowerShell

Git ya está inicializado en esta copia, en la rama `main`, con un commit inicial.
Instala GitHub CLI si todavía no está disponible:

```powershell
winget install --id GitHub.cli --exact --source winget
```

Cierra y abre la terminal después de instalarlo. Desde la raíz de esta copia:

```powershell
gh auth login --hostname github.com --git-protocol https --web --scopes workflow
gh auth setup-git
gh repo create app_deeplearning --private --source=. --remote=origin --push
gh repo view --web
```

Completa el inicio de sesión de GitHub en el navegador. El comando `gh repo create`
se ejecuta una vez; si el nombre ya existe en tu cuenta, revisa ese repositorio antes
de continuar. No se debe forzar un push ni sobrescribir su historial.

Para subir cambios posteriores, trabaja dentro de esta copia:

```powershell
git status
git add .
git commit -m "Actualiza el proyecto"
git push
```

El workflow raíz `.github/workflows/construir-apk.yml` usa la ruta de la aplicación
dentro de este repositorio completo. Se puede ejecutar desde Actions. Su compilación
remota no se ha verificado durante la preparación del repositorio.

Más detalles: [reconocimiento mejorado](MEJORAS_RECONOCIMIENTO.md),
[instalación del dataset](INSTALACION_INTEGRACION.md) y
[documentación de la API](proyecto-api-vision/README.md).
