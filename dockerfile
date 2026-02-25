FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalamos dependencias primero para aprovechar el cache de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto del proyecto
COPY . .

# AJUSTE PARA RAILWAY:
# Usamos el formato de "shell" (sin corchetes) para que Docker pueda 
# interpretar la variable de entorno $PORT que nos da Railway.
CMD gunicorn config.wsgi:application --bind 0.0.0.0:$PORT