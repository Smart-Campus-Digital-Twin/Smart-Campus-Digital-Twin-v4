FROM python:3.12-slim

WORKDIR /app

# Install deps first (layer cache)
COPY processing/consumer/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy source — include parent package so imports resolve
COPY processing/ ./processing/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 9091

CMD ["python", "-m", "processing.consumer.main"]
