import os
import csv
import shutil
import uuid
import sys
import unicodedata

CSV_FILE = "sujetos.csv"
DATA_DIR = "data/images"

def normalizar(nombre):
    # Estandariza para la búsqueda interna (ej. "Juan Pérez" -> "juan_perez")
    n = unicodedata.normalize('NFKD', nombre).encode('ASCII', 'ignore').decode('utf-8')
    return n.lower().strip().replace(" ", "_")

def obtener_o_crear_id(nombre_original):
    nombre_norm = normalizar(nombre_original)
    registros = []
    
    # Leer el CSV si existe
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            registros = list(reader)
            
            # Buscar si la persona ya existe
            for fila in registros:
                if fila['nombre_normalizado'] == nombre_norm:
                    print(f"Búsqueda: {nombre_original} ya existe -> {fila['id_carpeta']}")
                    return fila['id_carpeta']
    
    # Si no existe, crear un nuevo ID
    nuevo_numero = len(registros) + 1
    nuevo_id = f"persona{nuevo_numero:03d}" # Genera persona001, persona002...
    
    # Guardar en el CSV
    es_nuevo_archivo = not os.path.exists(CSV_FILE)
    with open(CSV_FILE, mode='a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if es_nuevo_archivo:
            writer.writerow(['id_carpeta', 'nombre_normalizado', 'nombre_original'])
        writer.writerow([nuevo_id, nombre_norm, nombre_original])
        
    print(f"Nuevo registro creado: {nombre_original} -> {nuevo_id}")
    return nuevo_id

def procesar_fotos(nombre_persona, carpeta_origen):
    if not os.path.exists(carpeta_origen):
        print("La carpeta de origen no existe.")
        return

    # 1. Identificar a la persona y su carpeta destino
    id_carpeta = obtener_o_crear_id(nombre_persona)
    ruta_destino = os.path.join(DATA_DIR, id_carpeta)
    os.makedirs(ruta_destino, exist_ok=True)
    
    # 2. Copiar fotos con nombres únicos (UUID) para evitar sobrescrituras
    archivos = [f for f in os.listdir(carpeta_origen) if os.path.isfile(os.path.join(carpeta_origen, f))]
    
    for archivo in archivos:
        _, extension = os.path.splitext(archivo)
        nombre_unico = f"{uuid.uuid4().hex}{extension.lower()}"
        
        origen_path = os.path.join(carpeta_origen, archivo)
        destino_path = os.path.join(ruta_destino, nombre_unico)
        
        shutil.copy2(origen_path, destino_path)
        
    print(f"Éxito: Se copiaron {len(archivos)} fotos en {ruta_destino}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python ingestar_datos.py \"Nombre Persona\" ./ruta_a_las_fotos")
    else:
        procesar_fotos(sys.argv[1], sys.argv[2])