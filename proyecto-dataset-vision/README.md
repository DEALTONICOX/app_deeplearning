# 📸 Manual de Integración - DataOps (Rama `integracion`)

Actualmente, esta rama contiene nuestro **Producto Mínimo Viable (MVP)**: un dataset base funcional con más de 30 sujetos y 300 imágenes. 

**Tu misión como Integrador:** Descargar los Pull Requests (PR) pendientes, auditarlos, resolver los conflictos de fusión y añadirlos a este dataset unificado.

---

## 🚨 Control de Calidad: Errores Frecuentes

Antes de aceptar un PR, revisa estos 3 problemas comunes:

1. **Choque de Iniciales (Intersecciones):** Si el PR trae a un sujeto llamado "Michelle Ferraro" (`mf_01`), pero en nuestro dataset ya existe "Matías Figueroa" (`mf_01`), debes cambiar el ID del nuevo a `mf_02` en el CSV y renombrar su carpeta de fotos.
2. **Columnas Invertidas o Mal Formateadas:** Revisa el `sujetos.csv`. El orden estricto debe ser: `id_carpeta,nombre_normalizado,nombre_original` (separado por comas, sin espacios después de la coma).
3. **Imágenes Huérfanas:** Revisa que en `data/images/` no haya fotos sueltas. Todas deben estar dentro de la carpeta de su respectivo sujeto.

---

## 🛠️ Apuntes del Tech Lead: Flujo de Trabajo

Usa esta guía de comandos para evaluar cada Pull Request paso a paso. *(Reemplaza `NUMERO` por el ID del PR que vas a revisar)*.

### 1. Preparar y Descargar
```bash
source .venv/bin/activate
git checkout main
git fetch origin pull/NUMERO/head:revision_pr_NUMERO
git checkout revision_pr_NUMERO
dvc pull
```

### 2. Inspección Visual
Revisa en tu editor de código:
- `sujetos.csv`
- `data/images`

---

### 3. Decisión y Ejecución

#### CAMINO A: Tiene errores (Rechazar y Limpiar)
Si la estructura está mal o fallan las imágenes, avisa en GitHub y limpia tu entorno local:
```bash
git checkout main
git clean -fd
git branch -D revision_pr_NUMERO
```

#### CAMINO B: Perfecto (Integrar a la recolección)
Si todo está correcto, fusiónalo en nuestra rama de integración. **Aparecerán conflictos en el CSV y en DVC, es normal.**

```bash
# 1. Traer los datos a la rama de integración
git checkout integracion
git merge revision_pr_NUMERO

# 2. RESOLVER EL CSV MANUALMENTE
# (Abre sujetos.csv, borra las marcas de conflicto y ordena las filas)

# 3. RESOLVER DVC (Recalcular imágenes)
rm data/images.dvc
dvc add data/images

# 4. Sellar la integración y subir a la nube
git add sujetos.csv data/images.dvc
git commit -m "Integra PR NUMERO a la recoleccion"
git push origin integracion

# 5. Limpiar el entorno
git branch -D revision_pr_NUMERO
```
