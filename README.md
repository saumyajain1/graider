# Graider

Graider helps teachers turn assignments into structured questions, prepare reference answers and rubrics, grade student submissions, and review the results before exporting them.

[Live demo](https://graider-xt2w.onrender.com/login) · [Docker image](https://hub.docker.com/r/saumyaj1/graider) · [Documentation](#documentation)

The demo runs on a sleeping free service; the first visit can be slow. Use sample student data.

## Features

- Create assignments from text, TXT files or PDFs, with editable questions and mark allocations.
- Generate reference answers and rubrics with AI, or write them manually.
- Import submissions individually, from files or through CSV.
- Grade with AI against the saved reference answer and every rubric criterion; review and edit criterion scores and feedback with calculated totals.
- Run AI actions in persistent background jobs, with progress, cancellation, controlled retries and recovery after restart.
- Publish each student's complete result independently while other students continue grading.
- Sign in with passwords or Google, explicitly connect accounts, and manage profile and credentials.
- Keep uploads private and enforce teacher access, upload limits and AI usage quotas.
- Explore the automatically generated API through Swagger UI at `/api/docs/`.

## Engineering results

- A **production 10-student × 10-question grading run finished in 1 minute 54 seconds**, including answer mapping and **110 real OpenAI calls**, on Render's **0.1-CPU / 512-MB Free service**; sampled peak memory was **313.8 MiB**.
- Container restart preserved **100 question results, 200 criterion breakdowns and 110 successful usage records**, without repeating provider calls.
- Process-death and connection-loss checks cover checkpoint recovery, atomic publication, concurrent workers and uncertain billing.
- GitHub Actions verifies the repository, publishes Docker images for Intel/AMD and Apple Silicon, and triggers Render with the passing commit image.

The production benchmark uses short synthetic arithmetic answers, real GPT-6 Luna and Neon PostgreSQL; setup and startup are outside its timer. Local concurrency and process-failure experiments use simulated calls. See [benchmarks and their limits](docs/BENCHMARKS.md).

## Tech stack

| Layer                 | Technology                                                                                   |
| --------------------- | -------------------------------------------------------------------------------------------- |
| Frontend              | React, TypeScript, Vite, Tailwind CSS                                                        |
| Backend               | Django, Django REST Framework, Gunicorn, WhiteNoise                                          |
| Identity and API docs | django-allauth, Google OIDC, drf-spectacular                                                 |
| Persistence           | Neon PostgreSQL and private S3-compatible Object Storage; SQLite/local files for development |
| AI                    | OpenAI SDK, task-specific model and reasoning configuration                                  |
| Delivery              | Docker, Docker Hub, GitHub Actions, Render                                                   |

## Documentation

| Page                                                         | Contents                                                                                            |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- |
| [Architecture](docs/ARCHITECTURE.md)                         | System and data diagrams, component boundaries, security and design decisions                       |
| [Grading workflow](docs/GRADING.md)                          | Assignment preparation, answer mapping, criterion scoring, concurrency, recovery and teacher review |
| [Benchmarks](docs/BENCHMARKS.md)                             | Current and historical grading timings, test conditions, recovery evidence and reproduction         |
| [Setup and deployment](docs/SETUP.md)                        | Docker quickstart, source development, environment settings, accounts, Render and maintenance       |
| [Issues and roadmap](docs/ROADMAP.md)                        | Unresolved limitations, upcoming features and proposed improvements                                 |
| [Production grading report](docs/ai-grading-production.json) | Real-provider timings, resource samples, usage and restart evidence                                 |
| [Raw grading benchmarks](docs/ai-grading-concurrency.json)   | Concurrency experiments, isolated grading measurements and runtime image ID                         |
| [Earlier capacity report](docs/ai-job-capacity.json)         | Historical full-workflow, startup and restart measurements                                          |

These pages describe this checkout; the deployed demo and published `latest` image may lag it.

Start with the [Docker quickstart](docs/SETUP.md#run-locally-with-docker) to use the app, or [source development](docs/SETUP.md#develop-from-source) to change it.
