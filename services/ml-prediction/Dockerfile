FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/ml-prediction/prediction_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/ml-prediction/prediction_service/ ./

EXPOSE 8001
CMD ["python", "main.py"]
