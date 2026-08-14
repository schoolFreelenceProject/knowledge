FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
ARG INSTALL_OLLAMA_CLIENT=false
ARG INSTALL_PDF_OCR=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates poppler-utils \
    && if [ "$INSTALL_PDF_OCR" = "true" ]; then \
        apt-get install -y --no-install-recommends \
          tesseract-ocr tesseract-ocr-eng tesseract-ocr-jpn; \
    fi \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ollama.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt \
    && if [ "$INSTALL_OLLAMA_CLIENT" = "true" ]; then \
        python -m pip install -r requirements-ollama.txt; \
    fi

COPY app ./app
COPY scripts ./scripts
COPY alembic.ini .
COPY alembic ./alembic

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
