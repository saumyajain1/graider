# Base-image digests keep the build runtime fixed; update them with dependencies.
FROM node:24-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6 AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PIP_DISABLE_PIP_VERSION_CHECK=1 \
  DJANGO_DEBUG=false
WORKDIR /app/backend
COPY backend/requirements.txt backend/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt -c requirements.lock
COPY backend/ ./
COPY --from=frontend /build/frontend/dist /app/frontend/dist
# Static collection needs no database, storage credentials, or OpenAI key.
RUN DJANGO_DEBUG=true DJANGO_SECRET_KEY=build-only-static-collection \
  python manage.py collectstatic --noinput \
  && useradd --create-home --user-group --uid 10001 graider \
  && chown -R graider:graider /app
USER 10001:10001
EXPOSE 10000
CMD ["sh", "/app/backend/start.sh"]
