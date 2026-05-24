FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn python-multipart

COPY server.py .
COPY index.html .

RUN mkdir -p /app/uploads

EXPOSE 8849

CMD ["python3", "server.py"]
