# АИС «Техноконтур» — бэкенд (FastAPI + SQLAlchemy)
# Production-образ: slim, non-root, healthcheck. Вариант Б: базовый образ заменяется
# на сертифицированный (Astra Linux / ОС «Оникс») с СКЗИ-слоем.
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

WORKDIR /srv/technocontour

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# non-root (ФСТЭК: минимальные привилегии)
RUN useradd -r -u 10001 tc && chown -R tc:tc /srv/technocontour
USER tc

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/core/health',timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
