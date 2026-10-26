"""Respaldo local reproducible sin credenciales ni dependencias instaladas."""
import hashlib
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
OMITIR_DIRS = {'.git', 'venv', '.venv', 'env', 'node_modules', '__pycache__',
    '.gradle', 'build', 'registros_api_mejorada', '.pytest_cache', '.idea', '.aws', '.codex', '.agents'}
OMITIR_ARCHIVOS = {'config.local', 'gdrive-user.json', '.env', 'local.properties',
                   'credentials.json', 'client_secrets.json', '.DS_Store', 'Thumbs.db'}


def archivos():
    for carpeta in ('proyecto-api-vision', 'proyecto-dataset-vision', 'cuarentena_duplicados'):
        for actual, dirs, nombres in os.walk(RAIZ / carpeta):
            directorio = Path(actual)
            dirs[:] = sorted(d for d in dirs if d not in OMITIR_DIRS
                and not (directorio.name == '.dvc' and d in {'tmp', 'cache'})
                and not (directorio / d).is_symlink())
            for nombre in sorted(nombres):
                ruta = directorio / nombre
                if (nombre in OMITIR_ARCHIVOS or nombre.startswith('.env.')
                        or ruta.suffix.lower() in {'.pyc', '.mjpeg', '.log', '.pid', '.jks', '.keystore'}
                        or ruta.is_symlink()):
                    continue
                yield ruta
    for ruta in sorted(RAIZ.iterdir()):
        if ruta.is_file() and ruta.suffix.lower() in {'.md', '.ps1', '.py'}:
            yield ruta


def main():
    carpeta = RAIZ / 'respaldos'
    carpeta.mkdir(exist_ok=True)
    sello = datetime.now().strftime('%Y%m%d_%H%M%S')
    destino = carpeta / f'entrega_reconocimiento_{sello}.zip'
    temporal = destino.with_suffix('.parcial')
    registros = []
    with zipfile.ZipFile(temporal, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=5) as zip_salida:
        for ruta in archivos():
            relativo = ruta.relative_to(RAIZ)
            contenido = ruta.read_bytes()
            zip_salida.writestr('entrega_etapa_3_app/' + relativo.as_posix(), contenido)
            registros.append({'ruta': relativo.as_posix(), 'bytes': len(contenido),
                              'sha256': hashlib.sha256(contenido).hexdigest()})
        zip_salida.writestr('entrega_etapa_3_app/MANIFIESTO_RESPALDO.json', json.dumps(
            {'fecha_local': sello, 'dataset': '88 fotos limpias de 9 personas; integracion parcial',
             'archivos': registros}, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(temporal) as comprobacion:
        corrupto = comprobacion.testzip()
        if corrupto:
            raise ValueError('Archivo dañado en respaldo: ' + corrupto)
        for nombre in comprobacion.namelist():
            partes = Path(nombre).parts
            if any(p in OMITIR_DIRS or p in OMITIR_ARCHIVOS for p in partes):
                raise ValueError('Ruta excluida dentro del respaldo: ' + nombre)
        requeridos = ['proyecto-api-vision/salidas_mejoradas/galeria.npz',
            'proyecto-api-vision/modelos_rostro/face_recognition_sface_2021dec.onnx',
            'proyecto-api-vision/app-movil/www/index.html']
        if not all('entrega_etapa_3_app/' + n in comprobacion.namelist() for n in requeridos):
            raise ValueError('Faltan artefactos necesarios para restaurar.')
    temporal.replace(destino)
    huella = hashlib.sha256(destino.read_bytes()).hexdigest()
    destino.with_suffix('.zip.sha256').write_text(f'{huella}  {destino.name}\n', encoding='ascii')
    print(f'Respaldo: {destino}')
    print(f'Archivos: {len(registros)}; tamaño: {destino.stat().st_size / 1024**2:.1f} MiB')
    print('Verificado: integridad ZIP y ausencia de las rutas de credenciales excluidas.')


if __name__ == '__main__':
    main()
