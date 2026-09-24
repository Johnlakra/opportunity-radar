FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Render runs everything in one container; docker compose sets its own command per service.
CMD ["bash", "start.sh"]
