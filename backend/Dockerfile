# Build from the repo root:  docker build -f backend/Dockerfile -t nigraan-api .
ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/backend
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ /srv/backend/
COPY models/ /srv/models/
COPY demo_week/ /srv/demo_week/

ENV MODELS_DIR=/srv/models DEMO_WEEK_DIR=/srv/demo_week DATA_OUT_DIR=/tmp/nigraan_out PORT=8000
EXPOSE 8000
# One worker: models and the scoring cache live in process memory (~300 MB).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers"]
