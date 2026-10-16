FROM python:3.12.7-slim

# No .pyc writes (the container's root filesystem is read-only in docker-compose.yml) and unbuffered logs.
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

RUN useradd --system --uid 10001 --no-create-home app

WORKDIR /app
# Root-owned, so the app user cannot rewrite its own code.
COPY server.py .

USER 10001
EXPOSE 8000
CMD ["python", "server.py"]
