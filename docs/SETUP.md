# Local setup, deployment and operation

Use Docker to try Graider; use a source checkout for development. [.env.example](../.env.example) documents every environment variable with consistent quoted values and comments. Keep credentials in ignored dotenv files or hosting settings.

## Run locally with Docker

Requires Docker Desktop. The published image includes the frontend, Django, Gunicorn and AI worker; Python/Node and a repository checkout are unnecessary.

```sh
mkdir graider-demo
cd graider-demo
curl -fsSL https://raw.githubusercontent.com/saumyajain1/graider/main/compose.yaml -o compose.yaml
curl -fsSL https://raw.githubusercontent.com/saumyajain1/graider/main/.env.example -o .env
```

Set a unique `DJANGO_SECRET_KEY` in `.env`. Add `OPENAI_API_KEY` to use AI, or leave it blank for manual workflows. Keep database/storage credentials blank for local use.

```sh
docker compose up -d
```

Open [localhost:8000](http://localhost:8000). Compose uses SQLite and persistent upload/database volumes and starts web/worker automatically. SQLite runs AI steps sequentially. `docker compose down` stops containers while retaining data; `docker compose down --volumes` deletes those volumes. Inspect output with `docker compose logs -f graider`.

Update with `docker compose pull` and `docker compose up -d`. `GRAIDER_IMAGE_TAG=latest` selects the released image; `sha-<commit>` selects an exact release. Published images support Intel/AMD and Apple Silicon and can lag an unreleased source checkout. To test this checkout locally, run `docker build -t saumyaj1/graider:local .` and set `GRAIDER_IMAGE_TAG="local"` before starting Compose.

## Develop from source

Use Python 3.11 and Node.js 24:

```sh
git clone https://github.com/saumyajain1/graider.git
cd graider
cp .env.example .env
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt -c backend/requirements.lock
npm ci --prefix frontend
```

Set a unique secret and an optional OpenAI key. Keep `DATABASE_URL` and storage credentials empty for SQLite/local files. Use three terminals, activating the virtual environment in each Python terminal:

```sh
# Terminal 1: HTTP API
python backend/manage.py migrate
python backend/manage.py runserver 127.0.0.1:8000
```

```sh
# Terminal 2: AI worker, with the same root .env as Django
python backend/manage.py run_ai_worker
```

```sh
# Terminal 3: frontend
npm run dev --prefix frontend
```

Open [localhost:5173](http://localhost:5173). Vite proxies `/api` and `/accounts` to Django. Use PostgreSQL via `DATABASE_URL` to exercise concurrent jobs; SQLite intentionally executes one AI step at a time. Separate local app instances require distinct `GRAIDER_AI_WAKE_SOCKET` paths, ports and databases.

Install quality dependencies and run checks from the repository root:

```sh
python -m pip install -r backend/requirements-dev.txt
npm ci
npm run check
npm run test --prefix frontend
npm run build --prefix frontend
```

`npm run format` applies formatting. Docker must run for Dockerfile/workflow linters. Run backend tests against local SQLite without cloud credentials:

```sh
DATABASE_URL= DJANGO_DEBUG=true AWS_ENDPOINT_URL_S3= AWS_ACCESS_KEY_ID= AWS_SECRET_ACCESS_KEY= \
  OPENAI_API_KEY= python backend/manage.py test apps config
```

PostgreSQL-specific concurrency tests require a disposable PostgreSQL database; see [benchmarks](BENCHMARKS.md#reproduce-the-current-checks). No test command should point to the production database.

## Deploy on Render

The supplied [render.yaml](../render.yaml) describes the service. For manual setup:

1. Prepare a Neon PostgreSQL database and private `uploads` bucket on the same branch. The supplied configuration uses AWS US East 2 (Ohio).
2. In Render choose **New → Web Service → Existing Image** and enter `docker.io/saumyaj1/graider:latest`. Choose the Free instance for the demo, Ohio region and health check `/health/`. Leave the Docker command override empty.
3. Add production environment values below. **Add from .env** can import a dotenv file, but replace local-development values first. Do not upload credentials to the repository.
4. Deploy. Startup applies migrations and checks settings, then supervises Gunicorn and the AI worker. Existing accounts, files and grades are preserved; never reset the live database.
5. Check `/health/`, login and a sample AI action. A successful HTTP health check does not prove worker readiness: AI admission returns `503` if the worker is unavailable. Verify progress, complete student publication and saved-job recovery after restart.

Render's [prebuilt-image documentation](https://render.com/docs/deploying-an-image) explains service creation and deploy hooks. Updating a registry tag alone does not redeploy an image-backed service; the configured GitHub workflow calls the hook. Its [free-service limitations](https://render.com/docs/free) include sleep and an ephemeral filesystem. Database/files live in Neon; work stops during sleep and resumes after incoming traffic wakes the service.

| Setting                                                                      | Production value                                                                               |
| ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `DJANGO_DEBUG`                                                               | `false`                                                                                        |
| `DJANGO_SECRET_KEY`                                                          | Unique random secret, at least 50 characters                                                   |
| `DJANGO_ALLOWED_HOSTS`                                                       | Empty on Render if using its automatically detected hostname; list custom hostnames explicitly |
| `DATABASE_URL`                                                               | Neon PostgreSQL URL with required TLS, including `sslmode=require`                             |
| `AWS_ENDPOINT_URL_S3`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`          | Neon Object Storage endpoint and credentials                                                   |
| `AWS_REGION`, `NEON_STORAGE_BUCKET`                                          | `us-east-2`, `uploads`                                                                         |
| `GRAIDER_AI_JOBS_ENABLED`                                                    | `true`                                                                                         |
| `OPENAI_API_KEY`                                                             | Dedicated project key with access to the configured models                                     |
| `FRONTEND_URL`, `DJANGO_CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | Empty for a single-origin deployment                                                           |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`                                   | Optional matching production Google client                                                     |
| `BREVO_API_KEY`, `GRAIDER_FROM_EMAIL`                                        | Optional verified email configuration for password recovery                                    |

Other settings retain the defaults in `.env.example`. Existing explicit environment values override code defaults. The `AWS_` names belong to the S3-compatible client; use Neon credentials rather than AWS credentials. Keep the bucket private.

Model and reasoning settings are grouped by task. The current defaults select GPT-6 Luna, medium reasoning for extraction/artifacts/grading and low for mapping/question repair. Use model identifiers and reasoning levels supported by your account. Application token/rate quotas complement the provider project's spending controls; they do not independently enforce a dollar-denominated budget. The demo's dedicated project was configured with a $5 monthly hard cap and lower-usage alerts.

## Google sign-in and account administration

Google login is optional; password accounts work without it. In [Google Auth Platform](https://console.cloud.google.com/auth/overview), configure branding, an External audience and a Web application client. Request only `openid`, email and profile identity scopes. Separate development/production clients or projects keep callbacks and secrets distinct. Google's [OIDC documentation](https://developers.google.com/identity/openid-connect/openid-connect) describes the identity protocol.

Register the exact callback for each browser origin you use:

| Environment                | Authorized redirect URI                                             |
| -------------------------- | ------------------------------------------------------------------- |
| Docker                     | `http://localhost:8000/accounts/google/login/callback/`             |
| Source frontend            | `http://localhost:5173/accounts/google/login/callback/`             |
| Source Django/admin origin | `http://127.0.0.1:8000/accounts/google/login/callback/`             |
| Current hosted demo        | `https://graider-xt2w.onrender.com/accounts/google/login/callback/` |

For a different host, replace the origin and retain `/accounts/google/login/callback/`. `localhost` and `127.0.0.1` have different cookies and require separate registrations. Use a consistent hostname throughout a login flow.

Set both `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in the environment and restart. In production branding, use the service's `/about/` homepage and `/privacy/` policy; complete required branding fields and publish the external audience for general sign-in. Missing credentials disable Google login.

New users can register/sign in with Google. Existing password users sign in first, then choose **Profile → Manage account → Connect Google**. Matching emails alone never merge accounts. Disconnecting requires a confirmed password; Google-only users need mailbox recovery to establish one first. Name/password edits preserve assignments and grades.

Admin is at `/admin/` on the Django/service origin (port 8000 for source development). Create an initial staff administrator inside the backend/container:

```sh
python backend/manage.py createsuperuser
# Docker alternative:
docker compose exec graider python manage.py createsuperuser
```

Admin Google sign-in requires an active, existing staff account with Google already connected and a callback registered for that admin origin. It cannot register accounts, link by matching email or grant staff permissions.

## Password recovery

Render's free service blocks SMTP ports, so Graider uses [Brevo's HTTPS transactional API](https://developers.brevo.com/reference/send-transac-email). Activate a Brevo account, verify a sender and create an API key rather than an SMTP key. Provider account/delivery limits apply; no fixed free allowance is assumed here.

Set `BREVO_API_KEY` and `GRAIDER_FROM_EMAIL="Graider <your-verified-sender@example.com>"`, then restart/redeploy. Request a reset from **Forgot your password?** and check delivery/spam and Brevo's transactional logs. Production without email credentials reports recovery unavailable. With `DJANGO_DEBUG=true` and no key, reset emails print to the terminal or `docker compose logs graider`; printed links are credentials.

Links expire after one hour and become invalid after password change. Tokens use the URL fragment rather than the portion sent to web-server logs. A generic request response avoids revealing registered emails and does not confirm delivery. Recovery invalidates sessions; an authenticated password change preserves the current session while invalidating others. Keep `FRONTEND_URL` empty for normal same-origin production reset links.

## CI/CD and API documentation

Configure repository-level GitHub **Settings → Secrets and variables → Actions**:

| Type     | Name                 | Value                                          |
| -------- | -------------------- | ---------------------------------------------- |
| Variable | `DOCKERHUB_USERNAME` | `saumyaj1`                                     |
| Secret   | `DOCKERHUB_TOKEN`    | Docker Hub Read/Write personal access token    |
| Secret   | `RENDER_DEPLOY_HOOK` | Deploy Hook URL from Render's service Settings |

Keep the image repository public for credential-free local/Render pulls. Docker Desktop login does not authenticate GitHub Actions. PR/feature checks verify lint/format, backend/frontend tests, builds, generated schema, supervised jobs and container persistence/recovery. Passing main merges publish `sha-<commit>` images for both architectures; the newest passing main merge also updates `latest`. The hook receives the exact passing commit image. Without the hook, publication succeeds but automatic deployment is skipped. Retain old commit images needed for compatible rollback.

Open `/api/docs/` on the running service for Swagger UI and `/api/schema/` for generated OpenAPI. The pages are public; authenticated operations require login, CSRF and ownership. **Try it out** uses the current browser session. Custom API actions declare serializers in their code; no separate OpenAPI document is manually maintained. CI regenerates and validates it.

## Background-job settings

Web and worker must share the database, feature flag and socket path. All fifteen controls have comments in `.env.example`:

| Setting                            | Default                       | Purpose                                                               |
| ---------------------------------- | ----------------------------- | --------------------------------------------------------------------- |
| `GRAIDER_AI_JOBS_ENABLED`          | `true`                        | Accept and execute jobs; false pauses AI with no synchronous fallback |
| `GRAIDER_AI_CONCURRENCY`           | `3`                           | Global simultaneous AI calls across workers                           |
| `GRAIDER_AI_STUDENT_CONCURRENCY`   | `3`                           | Rolling active-student limit, still bounded by the call cap           |
| `GRAIDER_AI_LEASE_SECONDS`         | `90`                          | Recovery deadline for abandoned claims                                |
| `GRAIDER_AI_HEARTBEAT_SECONDS`     | `10`                          | Live claim renewal interval; lease must exceed three intervals        |
| `GRAIDER_AI_SCAN_SECONDS`          | `2`                           | Queue-scan wait while runnable work exists; no periodic idle DB scans |
| `GRAIDER_AI_FAIRNESS_SECONDS`      | `30`                          | Waiting threshold for priority promotion                              |
| `GRAIDER_AI_SAFE_RETRIES`          | `2`                           | Automatic retries of safe rejections; zero disables them              |
| `GRAIDER_AI_RETRY_SECONDS`         | `10`                          | Initial retry delay; later waits increase exponentially               |
| `GRAIDER_AI_DRAIN_SECONDS`         | `20`                          | Shutdown grace for in-flight work                                     |
| `GRAIDER_AI_WAKE_SOCKET`           | `/tmp/graider-ai-worker.sock` | Private local web-to-worker channel                                   |
| `GRAIDER_AI_USER_QUEUE_LIMIT`      | `20`                          | Unfinished jobs per teacher, including paused jobs                    |
| `GRAIDER_AI_GLOBAL_QUEUE_LIMIT`    | `50`                          | Unfinished jobs across teachers; batch parents excluded               |
| `GRAIDER_AI_MAX_BATCH_SUBMISSIONS` | `10`                          | Students accepted in one batch                                        |
| `GRAIDER_AI_MAX_GRADING_QUESTIONS` | `10`                          | Scored questions per graded submission                                |

## Maintenance and recovery

Set `GRAIDER_AI_JOBS_ENABLED=false` and restart both processes together to pause AI. The container runs only Gunicorn; new AI actions/Resume return `503`, while login, manual edits, results, exports and job history remain available. Restore true and restart to recover compatible saved work.

| Job state or symptom                | Action                                                                       |
| ----------------------------------- | ---------------------------------------------------------------------------- |
| `queued`, `running`, `retry_wait`   | Allow the worker to proceed and poll visible progress                        |
| `paused_quota`                      | Restore allowance or wait for reset, then Resume                             |
| `needs_attention` / possible charge | Review before explicitly accepting a potentially charged retry               |
| Unsupported version                 | Run a compatible worker or cancel/start new work; do not edit saved versions |
| `failed`                            | Correct the cause and Resume if inputs remain compatible                     |
| `superseded`                        | Start new work against current inputs                                        |
| `cancelled`                         | No further publication; published student results remain                     |
| Admission `503`                     | Check maintenance flag, worker logs and shared socket/database               |

Prefer pausing the current image when diagnosing a fault. Rollback images must support the stored snapshot/prompt/output versions and asynchronous API. Older synchronous images are not compatible rollback targets. Current job versions are all 1. Do not force replay by editing snapshots/checkpoints. Closing the browser does not cancel a job, but execution cannot continue while Render itself is stopped.

Preview old job-record cleanup:

```sh
python backend/manage.py prune_ai_jobs
```

Only apply after checking the selected database and preview:

```sh
python backend/manage.py prune_ai_jobs --days 30 --batch-size 100 --apply
```

Cleanup considers finished succeeded/failed/cancelled/superseded trees older than 30 days. Active, paused, attention-required, recent, unknown or unfinished child records remain; active targets, running steps and pending usage also protect a tree. Transactions delete at most 100 root trees per batch. Cleanup removes job snapshots/checkpoints/attempts but preserves published data, uploads and all usage accounting, including uncertain reservations. Old Resume/idempotency history disappears with a removed tree. No automatic cleanup schedule or recurring hosting renewal is configured.
