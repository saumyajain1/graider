# Graider

Graider is a personal project for AI-assisted grading. Teachers create assignments, prepare reference answers and rubrics, grade submissions, and review results before exporting them.

## Features

- Create assignments from pasted text, TXT files, or PDFs.
- Generate questions, reference answers, and rubrics with configurable AI models and reasoning effort.
- Add student submissions individually or import a CSV; review scores and feedback before finalizing.
- Keep original uploads private, restrict access to their teacher, and enforce upload and AI token limits.

Built with session authentication and CSRF protection, persistent file storage, and CI covering 85 backend tests and production-server checks. This is a demo; use sample submissions rather than real student information.

## Tech stack

- **Frontend:** React, TypeScript, Vite, Tailwind CSS.
- **Backend:** Django, Django REST Framework, Gunicorn, WhiteNoise.
- **Data:** SQLite and local files for development; Neon PostgreSQL and private Object Storage in production.
- **AI:** OpenAI SDK; GPT-6 Luna by default, configurable per task.
- **Hosting:** one Docker web service on Render for the frontend and API.

## Run locally with Docker

Requires Docker Desktop. The published image includes the frontend and backend; no Python, Node.js, or repository checkout is needed.

```bash
mkdir graider-demo
cd graider-demo
curl -fsSL https://raw.githubusercontent.com/saumyajain1/graider/codex/graider-deployment/compose.yaml -o compose.yaml
curl -fsSL https://raw.githubusercontent.com/saumyajain1/graider/codex/graider-deployment/.env.example -o .env
```

Set a unique `DJANGO_SECRET_KEY` in `.env`; add `OPENAI_API_KEY` for AI features, or leave it empty for manual use. Then run:

```bash
docker compose up -d
```

Open [localhost:8000](http://localhost:8000). SQLite data and uploads persist in Docker volumes. `docker compose down` stops the app; adding `--volumes` deletes that local data. To update, run `docker compose pull` followed by `docker compose up -d`.

The `preview` image tracks the deployment branch. After the PR merges, `latest` is published from `main`; set `GRAIDER_IMAGE_TAG=latest` in `.env` to use it. Images support Intel/AMD and Apple Silicon.

## Deploy on Render

1. Use the published image; GitHub CI builds it only after all checks pass.
2. Create a Neon PostgreSQL database and a private `uploads` bucket on the same branch in AWS US East 2 (Ohio).
3. In Render, create a **Blueprint** from `codex/graider-deployment` using [render.yaml](render.yaml). It defines a free web service in Ohio that pulls the published image.
4. Supply the environment values below and deploy.

| Setting                                                                      | Production value                                                               |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `DJANGO_DEBUG`                                                               | `false`                                                                        |
| `DJANGO_SECRET_KEY`                                                          | A unique random secret of at least 50 characters                               |
| `DJANGO_ALLOWED_HOSTS`                                                       | Empty on Render (its assigned hostname is detected); list any custom hostnames |
| `DATABASE_URL`                                                               | Neon PostgreSQL connection URL, including `sslmode=require`                    |
| `AWS_ENDPOINT_URL_S3`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`          | Neon Object Storage endpoint and credentials                                   |
| `AWS_REGION`, `NEON_STORAGE_BUCKET`                                          | `us-east-2`, `uploads`                                                         |
| `OPENAI_API_KEY`                                                             | A dedicated OpenAI project key                                                 |
| `FRONTEND_URL`, `DJANGO_CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | Empty for this same-origin deployment                                          |

Enter credentials in Render's environment settings; do not upload `.env`. Set a monthly spend cap for the OpenAI project. [.env.example](.env.example) lists optional model, reasoning, upload, token quota, and server overrides.

The image contains the built frontend and static files. Startup applies pending migrations and runs Gunicorn; `/health/` checks availability. Redeploy manually on Render after publishing a new image; switch its image tag to `latest` after merging the PR. Use a fresh database for the initial deployment. Uploaded files persist in Neon rather than on Render's temporary filesystem.

## Develop from source

For live reload and code changes, use Python 3.11 and Node.js 24:

```bash
git clone --branch codex/graider-deployment https://github.com/saumyajain1/graider.git
cd graider
cp .env.example .env
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt -c backend/requirements.lock
npm ci --prefix frontend
```

Configure the two keys in `.env` as above; keep the database URL and storage credentials empty for local SQLite/files. Start the backend:

```bash
python backend/manage.py migrate
python backend/manage.py runserver 127.0.0.1:8000
```

In another terminal, run `npm run dev --prefix frontend` and open [localhost:5173](http://localhost:5173).

Install the quality tools:

```bash
python -m pip install -r backend/requirements-dev.txt
npm ci
```

Run `npm run check` for linting and formatting checks, or `npm run format` to apply formatting. Docker must be running for the Dockerfile and workflow linters. CI also runs backend tests, frontend builds, and container startup checks.

Run backend tests without connecting to cloud services:

```bash
cd backend
DATABASE_URL= AWS_ENDPOINT_URL_S3= AWS_ACCESS_KEY_ID= AWS_SECRET_ACCESS_KEY= \
  OPENAI_API_KEY= python manage.py test
```

CSV imports require `student_name` and `response_text` (or `raw_response_text`); `student_identifier` (or `student_id`) is optional.
