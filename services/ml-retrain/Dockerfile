FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/ml-retrain/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/ml-retrain/ .
COPY services/ml-prediction/datasets /app/datasets

CMD ["python", "scheduler.py"]
