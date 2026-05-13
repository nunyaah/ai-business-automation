FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
ENV DB_PATH=/data/tickets.db

VOLUME ["/data"]

EXPOSE 8002

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8002"]
