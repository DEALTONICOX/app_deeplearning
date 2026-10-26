# Imagen de la API de reconocimiento (solo lo necesario para servir, sin entrenar).
# Ejemplo local:   docker build -t api-rostros . && docker run -p 7860:7860 api-rostros
# Hugging Face Spaces (SDK Docker) usa el puerto 7860 por defecto.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 TF_CPP_MIN_LOG_LEVEL=2

RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY app.py preprocesamiento.py motor_rostros.py ./
COPY modelos_rostro/ modelos_rostro/
ARG ARTEFACTOS=salidas_mejoradas
COPY ${ARTEFACTOS}/ salidas/

EXPOSE 7860
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860}"]
