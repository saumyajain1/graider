# Graider

Graider is a personal project for AI-assisted grading. Teachers create assignments, prepare reference answers and rubrics, grade submissions, and review results before exporting them.

[Try the live demo](https://graider-xt2w.onrender.com/login). The free server sleeps when idle, so the first visit can take a minute or longer.

## Features

- Create assignments from pasted text, TXT files, or PDFs.
- Generate questions, reference answers, and rubrics with configurable AI models and reasoning effort.
- Add student submissions individually or import a CSV; review scores and feedback before finalizing.
- Keep original uploads private, restrict access to their teacher, and enforce upload and AI token limits.

Built with session authentication and CSRF protection, persistent file storage, and CI covering backend tests and production-server checks. This is a demo; use sample submissions rather than real student information.

## Tech stack

- **Frontend:** React, TypeScript, Vite, Tailwind CSS.
- **Backend:** Django, Django REST Framework, Gunicorn, WhiteNoise.
- **Data:** SQLite and local files for development; Neon PostgreSQL and private Object Storage in production.
- **AI:** OpenAI SDK; GPT-6 Luna by default, configurable per task.
- **Hosting:** one Docker web service on Render for the frontend and API.

## Architecture

Render serves the React app and Django API from one URL. Django stores assignments and grading results in Neon PostgreSQL, original uploads in a private Neon bucket, and calls OpenAI for AI tasks. Upload limits and per-user/global token quotas bound usage; an enforced OpenAI project spend cap limits monthly AI cost.

## Run locally with Docker

Requires Docker Desktop. The published image includes the frontend and backend; no Python, Node.js, or repository checkout is needed.

```bash
mkdir graider-demo
cd graider-demo
curl -fsSL https://raw.githubusercontent.com/saumyajain1/graider/feat/production-deployment/compose.yaml -o compose.yaml
curl -fsSL https://raw.githubusercontent.com/saumyajain1/graider/feat/production-deployment/.env.example -o .env
```

Set a unique `DJANGO_SECRET_KEY` in `.env`; add `OPENAI_API_KEY` for AI features, or leave it empty for manual use. Then run:

```bash
docker compose up -d
```

Open [localhost:8000](http://localhost:8000). SQLite data and uploads persist in Docker volumes. `docker compose down` stops the app; adding `--volumes` deletes that local data. To update, run `docker compose pull` followed by `docker compose up -d`.

The image is hosted on [Docker Hub](https://hub.docker.com/r/saumyaj1/graider). Use `latest` for the current release or `sha-<commit>` for an exact version. CI publishes a commit tag after checks pass; the newest passing merge to `main` updates `latest`. Images support Intel/AMD and Apple Silicon.

## Deploy on Render

1. Use the published Docker Hub image; GitHub Actions releases new images only after all checks pass.
2. Create a Neon PostgreSQL database and a private `uploads` bucket on the same branch in AWS US East 2 (Ohio).
3. In Render, select **New → Web Service → Existing Image** and enter `docker.io/saumyaj1/graider:latest`. Choose **Free**, region **Ohio**, and health check path `/health/`. Leave the Docker command override empty.
4. Add the environment values below, using **Add from .env** to paste a production-configured dotenv file if preferred, then deploy. [render.yaml](render.yaml) provides the same configuration for Blueprint setup.

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

Enter credentials in Render's environment settings. For dotenv import, use production values from the table rather than the local development defaults; quoted values are supported. Keep credential files out of Git. In OpenAI **Project settings → Limits → Spend → Edit spend limit**, set a monthly amount and enable **Enforce a hard limit**; alerts alone do not cap spending. Restrict project model access to the models configured in [.env.example](.env.example), which also lists reasoning, upload, token quota, and server overrides.

The image contains the built frontend and static files. Startup applies pending migrations and runs Gunicorn; `/health/` checks availability. GitHub Actions triggers Render after publishing when its deploy hook is configured below. Use a fresh database for the initial deployment. Uploaded files persist in Neon rather than on Render's temporary filesystem.

## API documentation

Open [Swagger UI](http://localhost:8000/api/docs/) to explore the API. Sign in to Graider first; **Try it out** uses your browser session and CSRF protection. The specification at `/api/schema/` is generated from the API serializers and views; CI validates it without a separately maintained OpenAPI file.

## CI/CD

Pull requests run lint, formatting, backend tests, frontend builds, and production/container checks. After a merge to `main`, GitHub Actions builds both image architectures, pushes `saumyaj1/graider:sha-<commit>`, updates `latest` for the newest passing merge, and triggers Render with that exact commit image. Merge builds queue instead of canceling each other.

Configure **GitHub → Settings → Secrets and variables → Actions**:

| Type     | Name                 | Value                                                   |
| -------- | -------------------- | ------------------------------------------------------- |
| Variable | `DOCKERHUB_USERNAME` | `saumyaj1`                                              |
| Secret   | `DOCKERHUB_TOKEN`    | Docker Hub personal access token with Read/Write access |
| Secret   | `RENDER_DEPLOY_HOOK` | Deploy Hook URL from the Render service's Settings page |

Keep the Docker Hub repository public so local users and Render can pull without credentials. Docker Desktop login is local to your computer; GitHub Actions uses its own token. Until the Render hook is added, the workflow publishes images and reports that deployment setup is pending.

## Develop from source

For live reload and code changes, use Python 3.11 and Node.js 24:

```bash
git clone --branch feat/production-deployment https://github.com/saumyajain1/graider.git
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
