"""Construye y evalúa la galería facial. Aumento agrupado por foto original, sin fuga entre pliegues."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import StratifiedKFold

from auditar_dataset import auditar, procedencia_repositorio
from motor_rostros import ExtractorRostros, MODELOS, puntuar, variantes


def decisiones(scores, umbral, margen):
    orden = np.sort(scores, axis=1)
    return (orden[:, -1] >= umbral) & (orden[:, -1] - orden[:, -2] >= margen)


def calibrar(consultas, y, vectores, etiquetas, grupos, permitidos, clases):
    conocidos, desconocidos, objetivos = [], [], []
    for g in permitidos:
        if consultas[g] is None:
            continue
        mascara = np.isin(grupos, permitidos) & (grupos != g)
        conocidos.append(puntuar(consultas[g], vectores[mascara], etiquetas[mascara], grupos[mascara], clases))
        mascara &= etiquetas != y[g]
        desconocidos.append(puntuar(consultas[g], vectores[mascara], etiquetas[mascara], grupos[mascara], clases))
        objetivos.append(y[g])
    conocidos, desconocidos = np.asarray(conocidos), np.asarray(desconocidos)
    correctos = conocidos.argmax(1) == objetivos
    mejor = None
    for umbral in np.linspace(0.363, 0.90, 100):
        for margen in (0.03, 0.05, 0.08, 0.10, 0.15):
            acepta = decisiones(conocidos, umbral, margen)
            falso = decisiones(desconocidos, umbral, margen).mean()
            if falso > 0.05:
                continue
            acierto = np.mean(acepta & correctos)
            clave = (float((acierto + 1 - falso) / 2), float(acierto), float(margen))
            if mejor is None or clave > mejor[0]:
                mejor = (clave, float(umbral), margen, float(falso), float(acierto))
    if mejor is None:
        raise ValueError('No se encontró un umbral que cumpla el límite de falsas aceptaciones.')
    return {'umbral_confianza': mejor[1], 'margen_minimo': mejor[2],
            'falsa_aceptacion_calibracion': mejor[3], 'conocidos_correctos_aceptados_calibracion': mejor[4]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--imagenes', type=Path, default=Path('../proyecto-dataset-vision/data/images'))
    parser.add_argument('--csv', type=Path, default=Path('datos_zip_20261022/sujetos_presentes.csv'))
    parser.add_argument('--salida', type=Path, default=Path('salidas_mejoradas'))
    args = parser.parse_args()
    procedencia = procedencia_repositorio(Path('../proyecto-dataset-vision'))
    auditoria = auditar(args.imagenes, args.csv)
    if auditoria['errores']:
        raise ValueError('\n'.join(auditoria['errores']))
    args.salida.mkdir(exist_ok=True, parents=True)
    nombres = [s['nombre_original'] for s in auditoria['personas']]
    indices = {s['id_carpeta']: i for i, s in enumerate(auditoria['personas'])}
    extractor = ExtractorRostros()
    consultas, etiquetas_fotos, vectores, etiquetas, grupos, fallos = [], [], [], [], [], []
    for g, registro in enumerate(auditoria['archivos']):
        clase = indices[registro['id_carpeta']]
        etiquetas_fotos.append(clase)
        with Image.open(registro['ruta']) as imagen:
            cara, motivo = extractor.alinear(imagen)
        if cara is None:
            consultas.append(None)
            fallos.append({'ruta': registro['ruta'], 'motivo': motivo})
        else:
            consultas.append(extractor.descriptor(cara))
            for variante in variantes(cara):
                vectores.append(extractor.descriptor(variante))
                etiquetas.append(clase)
                grupos.append(g)
        print(f"Preparando {g+1}/{len(auditoria['archivos'])}: {motivo}", flush=True)
    vectores, etiquetas, grupos = np.asarray(vectores), np.asarray(etiquetas), np.asarray(grupos)
    y = np.asarray(etiquetas_fotos)
    if set(etiquetas) != set(range(len(nombres))):
        raise ValueError('Alguna identidad quedó sin rostros detectables.')
    predicciones = np.full(len(y), -1)
    aceptados = np.zeros(len(y), dtype=bool)
    desconocidos_aceptados = np.zeros(len(y), dtype=bool)
    pliegues = []
    for numero, (ent, prueba) in enumerate(StratifiedKFold(5, shuffle=True, random_state=42).split(np.zeros(len(y)), y), 1):
        config = calibrar(consultas, y, vectores, etiquetas, grupos, ent, len(nombres))
        mascara = np.isin(grupos, ent)
        for g in prueba:
            if consultas[g] is None:
                continue
            scores = puntuar(consultas[g], vectores[mascara], etiquetas[mascara], grupos[mascara], len(nombres))
            predicciones[g] = scores.argmax()
            aceptados[g] = decisiones(scores[None], config['umbral_confianza'], config['margen_minimo'])[0]
            desconocida = mascara & (etiquetas != y[g])
            scores = puntuar(consultas[g], vectores[desconocida], etiquetas[desconocida], grupos[desconocida], len(nombres))
            desconocidos_aceptados[g] = decisiones(scores[None], config['umbral_confianza'], config['margen_minimo'])[0]
        acierto = float(np.mean(predicciones[prueba] == y[prueba]))
        pliegues.append({'accuracy': acierto, 'calibracion_solo_entrenamiento': config})
        print(f'Pliegue {numero}/5: {acierto:.1%}', flush=True)
    calibracion = calibrar(consultas, y, vectores, etiquetas, grupos, np.arange(len(y)), len(nombres))
    np.savez_compressed(args.salida/'galeria.npz', vectores=vectores, etiquetas=etiquetas, grupos=grupos)
    configuracion = {'motor': 'sface', 'numero_clases': len(nombres), 'forma_entrada': [128,128,3],
        **calibracion, 'procedencia_dataset': procedencia, 'dataset_parcial': True,
        'aumento_datos': {'variantes_por_original': 8, 'espejo_en_extraccion': True,
            'transformaciones': ['gamma','contraste','desenfoque','jpeg','rotacion'],
            'agrupadas_por_original': True}, 'tipo_puntuacion': 'similitud_coseno'}
    metricas = {'imagenes': len(y), 'personas': len(nombres), 'rostros_detectados': len(y)-len(fallos),
        'accuracy_validacion_cruzada': float(accuracy_score(y,predicciones)),
        'f1_macro': float(f1_score(y,predicciones,labels=list(range(len(nombres))),average='macro',zero_division=0)),
        'conocidos_correctos_aceptados': float(np.mean(aceptados & (predicciones==y))),
        'conocidos_aceptados_erroneamente': float(np.mean(aceptados & (predicciones!=y))),
        'desconocidos_simulados_rechazados': float(1-desconocidos_aceptados.mean()),
        'pliegues': pliegues, 'calibracion_final': calibracion,
        'limitacion': 'Fotos del ZIP; no es una evaluación de nuevas sesiones de cámara ni desconocidos externos.',
        'fallos_deteccion': fallos}
    archivos = {'configuracion.json': configuracion, 'metricas.json': metricas,
        'etiquetas.json': {str(i):n for i,n in enumerate(nombres)}, 'auditoria_dataset.json': auditoria,
        'modelos_preentrenados.json': json.loads((MODELOS/'procedencia.json').read_text())}
    for nombre, contenido in archivos.items():
        (args.salida/nombre).write_text(json.dumps(contenido,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.salida/'reporte_clasificacion.txt').write_text(classification_report(y,predicciones,
        labels=list(range(len(nombres))),target_names=nombres,zero_division=0),encoding='utf-8')
    print(json.dumps(metricas,ensure_ascii=False,indent=2),flush=True)


if __name__ == '__main__':
    main()
