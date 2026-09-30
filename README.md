# Graider

Graider is a personal project for AI-assisted grading. Teachers create assignments, prepare reference answers and rubrics, grade submissions, and review results before exporting them.

## Features

- Create assignments from pasted text, TXT files, or PDFs.
- Generate questions, reference answers, and rubrics with configurable AI models and reasoning effort.
- Add student submissions individually or import a CSV; review scores and feedback before finalizing.
- Keep original uploads private, restrict access to their teacher, and enforce upload and AI token limits.

Built with session authentication and CSRF protection, persistent file storage, and CI covering 83 backend tests and production-server checks. This is a demo; use sample submissions rather than real student information.

## Tech stack

- **Frontend:** React, TypeScript, Vite, Tailwind CSS.
- **Backend:** Django, Django REST Framework, Gunicorn, WhiteNoise.
- **Data:** SQLite and local files for development; Neon PostgreSQL and private Object Storage in production.
- **AI:** OpenAI SDK; GPT-6 Luna by default, configurable per task.
- **Hosting:** one Docker web service on Render for the frontend and API.

## Run locally

Use a repository checkout for development: it provides automatic frontend reloads and needs no cloud database or Docker. Requires Python 3.11 and Node.js 24.

```bash
git clone https://github.com/saumyajain1/graider.git
cd graider
cp .env.example .env
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt -c backend/requirements.lock
npm ci --prefix frontend
```

In `.env`, set `DJANGO_SECRET_KEY` to a unique value and add `OPENAI_API_KEY` to use AI features. Keep `DJANGO_DEBUG="true"`, `DATABASE_URL=""`, and the three storage endpoint/credential variables empty for local SQLite and file storage. All settings and defaults are in [.env.example](.env.example).

Initialize the database and start the backend:

```bash
python backend/manage.py migrate
python backend/manage.py runserver 127.0.0.1:8000
```

In a second terminal, from the repository root:

```bash
npm run dev --prefix frontend
```

Open [localhost:5173](http://localhost:5173). Manual editing works without an OpenAI key.

## Deploy on Render

1. Push the repository to GitHub.
2. Create a Neon PostgreSQL database and a private `uploads` bucket on the same branch in AWS US East 2 (Ohio).
3. In Render, create a **Blueprint** from the repository using [render.yaml](render.yaml). It defines a free Docker web service in Ohio.
4. Supply the environment values below and deploy.

| Setting                                                                      | Production value                                            |
| ---------------------------------------------------------------------------- | ----------------------------------------------------------- |
| `DJANGO_DEBUG`                                                               | `false`                                                     |
| `DJANGO_SECRET_KEY`                                                          | A unique random secret of at least 50 characters            |
| `DJANGO_ALLOWED_HOSTS`                                                       | Your Render hostname, without `https://` or a path          |
| `DATABASE_URL`                                                               | Neon PostgreSQL connection URL, including `sslmode=require` |
| `AWS_ENDPOINT_URL_S3`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`          | Neon Object Storage endpoint and credentials                |
| `AWS_REGION`, `NEON_STORAGE_BUCKET`                                          | `us-east-2`, `uploads`                                      |
| `OPENAI_API_KEY`                                                             | A dedicated OpenAI project key                              |
| `FRONTEND_URL`, `DJANGO_CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | Empty for this same-origin deployment                       |

Enter credentials in Render's environment settings; do not upload `.env`. Set a monthly spend cap for the OpenAI project. [.env.example](.env.example) lists optional model, reasoning, upload, token quota, and server overrides.

Render builds React and collects static files through the Dockerfile. Startup applies pending migrations and runs Gunicorn; `/health/` checks availability. Use a fresh database for the initial deployment. Uploaded files persist in Neon rather than on Render's temporary filesystem.

## Development checks

Install the quality tools once:

```bash
python -m pip install -r backend/requirements-dev.txt
npm ci
```

Run `npm run check` for linting and formatting checks, or `npm run format` to apply formatting. Docker must be running for the Dockerfile and workflow linters. CI also runs backend tests, frontend builds, and container startup checks.

Run backend tests without connecting to cloud services:

```bash
DATABASE_URL= AWS_ENDPOINT_URL_S3= AWS_ACCESS_KEY_ID= AWS_SECRET_ACCESS_KEY= \
  OPENAI_API_KEY= python backend/manage.py test
```

CSV imports require `student_name` and `response_text` (or `raw_response_text`); `student_identifier` (or `student_id`) is optional.
