# ZIP recibido el 22 de octubre de 2026

Se importó `Dataset_DeepLearning-20261022T143901Z-1-001.zip` usando los nombres e
IDs del CSV de la rama `integracion`, sin cambiar ese CSV ni `data/images.dvc`.

- El ZIP contiene 90 fotos de 9 personas, sin CSV.
- 80 fotos coinciden por píxeles con el dataset anterior de la API.
- Una misma foto aparece en `Luciano Alcantara/10.jpg` y `Matías Figueroa/04.jpg`.
  Ambas copias se apartaron a `cuarentena_duplicados/conflictos_zip_…` con su
  manifiesto de recuperación. No se eligió una identidad por su apariencia.
- Quedaron **88 fotos legibles, sin duplicados exactos, de 9 personas**. Luciano
  y Matias conservan 9 fotos cada uno; las otras siete personas tienen 10.
- La auditoría de los nueve sujetos presentes no tiene errores.
- Faltan **28 personas** del CSV completo de `integracion`.

Los originales permanecen en el ZIP. `importacion.json` registra su SHA-256, el
commit de referencia, los archivos importados, la coincidencia con las fotos
anteriores y la ubicación exacta de ambas copias apartadas.

`auditoria_integracion.json` evalúa las 37 personas y registra los faltantes.
`auditoria_presentes.json` y `sujetos_presentes.csv` describen únicamente el
subconjunto recibido; no sustituyen al CSV completo del repositorio.
`muestras_aumento.png` permite inspeccionar variantes de entrenamiento.

No se ejecutó `dvc add` ni `dvc push` con este subconjunto: hacerlo sobre la
carpeta parcial cambiaría la referencia de 300 archivos a una versión incompleta.
Tampoco se reemplazó el modelo de la API. Se puede evaluar un piloto de nueve
personas con el CSV parcial, identificado explícitamente como tal; para entrenar
el conjunto de 37 personas es necesario recibir las otras imágenes.
