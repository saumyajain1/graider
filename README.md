# Graider MVP

Graider is a local-first MVP for AI-assisted grading. It lets a teacher:

- register and sign in
- create an assignment from pasted text, `.txt`, or `.pdf`
- generate questions, reference answers, and rubric criteria with an OpenAI LLM
- add student submissions manually or by CSV
- run an AI grading pass
- review and edit scores and feedback
- finalize results and export a CSV

## Stack

- `backend/`: Django + Django REST Framework + SQLite locally or Neon PostgreSQL in production
- `frontend/`: React + Vite + Tailwind
- OpenAI models: `gpt-5.4-mini` for all current AI tasks

## Local setup

1. Copy `.env.example` to `.env` (or keep an existing `.env` and add missing settings).
2. Set `OPENAI_API_KEY` in `.env` and replace the example `DJANGO_SECRET_KEY` with a unique local value. Keep `DJANGO_DEBUG=true` to use local SQLite.
3. Create and activate a virtualenv, then install backend dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

4. Install frontend dependencies:

```bash
cd frontend
npm install
cd ..
```

5. Apply migrations:

```bash
.venv/bin/python backend/manage.py migrate
```

## Run locally

Start the backend:

```bash
.venv/bin/python backend/manage.py runserver 127.0.0.1:8000
```

Start the frontend:

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`.

## Production configuration (Step 1)

The backend reads a PostgreSQL `DATABASE_URL` when supplied. A populated local `DATABASE_URL` makes local commands use that database; leave it empty to use local SQLite. With `DJANGO_DEBUG=false`, the backend requires `DJANGO_SECRET_KEY`, explicit `DJANGO_ALLOWED_HOSTS` (hostnames only), and a PostgreSQL `DATABASE_URL`; it will not fall back to SQLite. Keep real values in Render environment settings, not in Git or the deployed `.env` file. Neon connection URLs normally include `sslmode=require`.

For the planned same-origin Render deployment, leave `FRONTEND_URL`, `DJANGO_CORS_ALLOWED_ORIGINS`, and `DJANGO_CSRF_TRUSTED_ORIGINS` empty. Set the latter two to comma-separated full origins only if a separate frontend needs access. Production enables HTTPS-aware proxy handling and secure session/CSRF cookies.

Apply Django migrations to a fresh PostgreSQL database before use. The existing local SQLite data is intentionally not copied.

## Private upload storage (Step 2)

Production requires a private Neon Object Storage bucket. Create or use the `uploads` bucket on the same Neon branch as `DATABASE_URL`, then set `AWS_ENDPOINT_URL_S3`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, and `NEON_STORAGE_BUCKET` in Render. For local testing against Neon, put the same values in the ignored `.env`; leave the three credential/endpoint values empty to use local file storage while `DJANGO_DEBUG=true`. Do not commit credentials. The backend rejects production startup if object storage is not configured.

Original assignment, submission, and CSV files are stored privately. Graider returns authenticated download paths; Neon download links are signed for 60 seconds after the requesting teacher's ownership is checked. Upload limits are configurable through the `GRAIDER_MAX_*` settings in `.env.example`. Apply Django's initial migrations before enabling uploads in production.

## Same-origin production build (Step 3)

Build React before collecting Django static files:

```bash
cd frontend
npm ci
npm run build
cd ..
.venv/bin/python backend/manage.py collectstatic --noinput
```

Django serves the React page for browser routes, and WhiteNoise serves its compiled assets from `/static/frontend/`. The API remains under `/api/` on the same origin; original uploads remain in private Neon storage. `GET /health/` provides a lightweight health check. The deployment build/start commands are configured in a later step.

## Authentication and security (Step 4)

Graider keeps Django session login. Login, registration, and logout require a CSRF token; the frontend obtains it from `GET /api/auth/me` and sends it with writes. Production requires HTTPS, sets secure cookies and browser security headers, and accepts only the hostnames in `DJANGO_ALLOWED_HOSTS`. The initial HSTS duration is one hour without subdomain or preload directives, suitable while using a Render-provided hostname.

Login, registration, and auth-status requests have basic per-IP limits. Their defaults are `10/min`, `5/hour`, and `120/min`; change `GRAIDER_LOGIN_RATE`, `GRAIDER_REGISTER_RATE`, and `GRAIDER_AUTH_CHECK_RATE` if needed. These use Django's local in-memory cache, so counters reset when the process restarts and are not a hard abuse or cost boundary. The global AI budget in Step 5 is the cost boundary.

## CSV format

Graider accepts CSV imports with:

- required: `student_name`
- required: `response_text` or `raw_response_text`
- optional: `student_identifier` or `student_id`

## Notes

- This is an MVP, not a production grading platform.
- AI features fail loudly if the OpenAI key is missing, but manual editing still works.
- The export endpoint is `GET /api/assignments/:id/export.csv`.
