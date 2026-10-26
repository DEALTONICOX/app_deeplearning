"""Descarga los modelos oficiales OpenCV y verifica sus hashes Git LFS."""
import hashlib
import json
import urllib.request
from pathlib import Path

BASE = 'https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/'
PESOS = 'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/'
MODELOS = [('face_detection_yunet', 'face_detection_yunet_2023mar.onnx'),
           ('face_recognition_sface', 'face_recognition_sface_2021dec.onnx')]


def main():
    destino = Path(__file__).resolve().parent / 'modelos_rostro'
    destino.mkdir(exist_ok=True)
    registros = []
    for carpeta, nombre in MODELOS:
        relativo = carpeta + '/' + nombre
        puntero = urllib.request.urlopen(BASE + relativo, timeout=40).read().decode()
        campos = dict(linea.split(' ', 1) for linea in puntero.strip().splitlines())
        esperado = campos['oid'].removeprefix('sha256:')
        ruta = destino / nombre
        if not ruta.exists() or hashlib.sha256(ruta.read_bytes()).hexdigest() != esperado:
            print('Descargando ' + nombre, flush=True)
            temporal = ruta.with_suffix('.descarga')
            with urllib.request.urlopen(PESOS + relativo, timeout=90) as respuesta, temporal.open('wb') as archivo:
                while bloque := respuesta.read(1024 * 1024):
                    archivo.write(bloque)
            if temporal.stat().st_size != int(campos['size']) or hashlib.sha256(temporal.read_bytes()).hexdigest() != esperado:
                raise ValueError('La descarga no coincide con el hash oficial: ' + nombre)
            temporal.replace(ruta)
        licencia = urllib.request.urlopen(BASE + carpeta + '/LICENSE', timeout=40).read()
        (destino / (carpeta + '_LICENSE')).write_bytes(licencia)
        registros.append({'nombre': nombre, 'url': PESOS + relativo, 'sha256': esperado, 'bytes': ruta.stat().st_size})
        print('Verificado ' + nombre, flush=True)
    (destino / 'procedencia.json').write_text(json.dumps(registros, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
