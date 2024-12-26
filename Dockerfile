FROM python:3.11.5-slim

WORKDIR /app
RUN pip install --no-cache-dir flask flask-cors firebase-admin google-cloud-firestore


COPY . .
CMD ["python", "service.py"]
