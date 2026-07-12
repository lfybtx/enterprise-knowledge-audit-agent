FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 fonts-wqy-microhei fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-db.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-db.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
