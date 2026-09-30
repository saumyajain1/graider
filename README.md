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
- OpenAI models: `gpt-6-luna` for all current AI tasks, with reasoning effort configured per task

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

Login, registration, and auth-status requests have basic per-IP limits. Their defaults are `10/min`, `5/hour`, and `120/min`; change `GRAIDER_LOGIN_RATE`, `GRAIDER_REGISTER_RATE`, and `GRAIDER_AUTH_CHECK_RATE` if needed. These use Django's local in-memory cache, so counters reset when the process restarts and are not a hard abuse or cost boundary. The PostgreSQL AI token quota and the OpenAI project spend limit provide the cost controls.

## AI usage safeguards (Step 5)

All AI workflows default to `gpt-6-luna`. The four `OPENAI_*_MODEL` settings select models for questions, artifacts (reference answers and rubrics), answer mapping, and grading. Reasoning effort is configured independently for each operation:

| Task | Environment setting | Default |
| --- | --- | --- |
| Extract questions | `OPENAI_QUESTION_REASONING_EFFORT` | `medium` |
| Repair extracted questions | `OPENAI_QUESTION_REPAIR_REASONING_EFFORT` | `low` |
| Generate reference answers | `OPENAI_REFERENCE_REASONING_EFFORT` | `medium` |
| Generate rubrics | `OPENAI_RUBRIC_REASONING_EFFORT` | `medium` |
| Match student answers to questions | `OPENAI_MAPPING_REASONING_EFFORT` | `low` |
| Grade student answers | `OPENAI_GRADING_REASONING_EFFORT` | `medium` |

Set these in the local `.env` or Render's environment settings and restart the backend after changes. [GPT-6 Luna supports](https://developers.openai.com/api/docs/models/gpt-6-luna) `none`, `low`, `medium`, `high`, `xhigh`, and `max`; an invalid value is rejected before reserving usage or calling OpenAI. Medium is the starting point for math, question structure, and grading decisions; low handles matching and small repairs. Higher effort can consume more reasoning tokens, which count toward the output ceiling and token quotas. These defaults have not yet been compared on live grading examples.

Every OpenAI request reserves a conservative token estimate in PostgreSQL before it starts. A short row lock serializes quota checks across users, and the provider call runs after that transaction ends. Graider records the operation, user, model, token counts, result, and provider request ID. It replaces the reservation with OpenAI's reported usage; if a timeout makes usage uncertain, it keeps the reservation until the applicable quota window ends. Automatic SDK retries are disabled to avoid duplicate spend after uncertain failures.

The configurable limits are `GRAIDER_USER_DAILY_TOKENS`, `GRAIDER_USER_MONTHLY_TOKENS`, `GRAIDER_GLOBAL_MONTHLY_TOKENS`, `GRAIDER_USER_AI_REQUESTS_PER_MINUTE`, and `GRAIDER_MAX_OUTPUT_TOKENS`. Each AI operation also has its own output ceiling. Grade-all is limited by `GRAIDER_MAX_GRADE_ALL_SUBMISSIONS` and `GRAIDER_MAX_GRADE_ALL_QUESTIONS`; recently completed grading is reused for `GRAIDER_GRADE_REPEAT_COOLDOWN_SECONDS`. Usage can be inspected in Django admin.

Before making Graider public, create a dedicated OpenAI API project and project key. In the API Platform, open **Project settings → Limits → Spend → Edit spend limit**, choose a monthly amount you are comfortable with, turn on **Enforce a hard limit**, and save. Restrict Model Usage to the models in `.env.example` where available, and optionally add spend alerts below the cap. Put only the project key in Render's `OPENAI_API_KEY` setting; keep it out of Git and the frontend. OpenAI says [hard-limit enforcement is not instantaneous](https://developers.openai.com/api/docs/guides/spend-limits), so spending can slightly exceed the configured amount.

The prelaunch schema change is folded into `backend/apps/grading/migrations/0001_initial.py`. The existing disposable Neon database needs a clean rebuild before this version is deployed; do not reset a database containing data to preserve.

## CSV format

Graider accepts CSV imports with:

- required: `student_name`
- required: `response_text` or `raw_response_text`
- optional: `student_identifier` or `student_id`

## Notes

- This is an MVP, not a production grading platform.
- AI features fail loudly if the OpenAI key is missing, but manual editing still works.
- The export endpoint is `GET /api/assignments/:id/export.csv`.
