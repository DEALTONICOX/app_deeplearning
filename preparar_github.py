"""Exporta una copia del proyecto lista para GitHub sin modificar los originales."""
import hashlib
import json
import os
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DESTINO = RAIZ / 'app_deeplearning'
CARPETAS = ('proyecto-api-vision', 'proyecto-dataset-vision',
            'dataset_pr5', 'cuarentena_duplicados')
OMITIR_DIRS = {'.git', 'venv', '.venv', 'env', 'node_modules', '__pycache__',
               '.gradle', 'build', '.pytest_cache', '.idea', '.aws', '.codex',
               '.agents', 'registros_api_mejorada', 'modernize'}
OMITIR_ARCHIVOS = {'config.local', 'gdrive-user.json', '.env', 'local.properties',
                   'credentials.json', 'client_secrets.json', 'google-services.json',
                   '.DS_Store', 'Thumbs.db', 'Desktop.ini'}
OMITIR_SUFIJOS = {'.pyc', '.pyo', '.mjpeg', '.log', '.pid', '.jks', '.keystore'}


def archivos():
    for nombre in CARPETAS:
        for base, dirs, nombres in os.walk(RAIZ / nombre):
            carpeta = Path(base)
            dirs[:] = sorted(d for d in dirs if d not in OMITIR_DIRS
                             and not (carpeta.name == '.dvc' and d in {'tmp', 'cache'})
                             and not (carpeta / d).is_symlink())
            for nombre_archivo in sorted(nombres):
                ruta = carpeta / nombre_archivo
                if (ruta.is_symlink() or nombre_archivo in OMITIR_ARCHIVOS
                        or nombre_archivo.startswith('.env.')
                        or ruta.suffix.lower() in OMITIR_SUFIJOS):
                    continue
                yield ruta
    for ruta in sorted(RAIZ.iterdir()):
        if ruta.is_file() and ruta.suffix.lower() in {'.md', '.ps1', '.py'}:
            yield ruta


def main():
    # No sobrescribir trabajo posterior dentro de la copia preparada.
    if DESTINO.exists():
        raise SystemExit(f'Ya existe {DESTINO}. Se conserva sin modificaciones.')
    fuentes = list(archivos())
    if any(p.stat().st_size >= 100 * 1024**2 for p in fuentes):
        raise SystemExit('Hay archivos de 100 MiB o más: revisar antes de exportar.')
    registros = []
    for fuente in fuentes:
        relativo = fuente.relative_to(RAIZ)
        salida = DESTINO / relativo
        salida.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fuente, salida)
        registros.append({'ruta': relativo.as_posix(), 'bytes': salida.stat().st_size,
                         'sha256': hashlib.sha256(salida.read_bytes()).hexdigest()})
    (DESTINO / 'MANIFIESTO_EXPORTACION.json').write_text(
        json.dumps({'dataset': '88 fotos limpias de 9 personas; conjunto completo pendiente',
                    'archivos': registros}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Copia preparada: {DESTINO}')
    print(f'Archivos copiados: {len(registros)}')
    print(f'Tamaño: {sum(r["bytes"] for r in registros) / 1024**2:.1f} MiB')


if __name__ == '__main__':
    main()
