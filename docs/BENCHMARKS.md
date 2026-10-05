# Grading benchmarks and recovery evidence

The recorded runs use synthetic submissions. Timed workload checks use simulated provider responses through the real OpenAI SDK; their results describe application scheduling, persistence and resource behavior, not real-model quality or latency. Cold readiness, request admission and job completion are separate measurements.

## Constrained 10 × 10 workload

Run date: **October 3, 2026**, America/Vancouver. The application ran its normal Docker supervisor, Gunicorn and worker with a hard **0.1 CPU, 512 MiB RAM and no extra swap** allowance. PostgreSQL ran outside the constrained container on the local machine. The [raw report](ai-job-capacity.json) records the image ID; the runtime corresponds to source revision `69917cf`.

The fixture had ten students, ten answered questions per student and two criteria per question. Each student made one mapping and ten grading calls: **110 calls, 100 question results and 200 criterion results**. Simulated calls took eight seconds; one student took ten seconds per call. Global call and student concurrency were three. Default token allowances and the 40-request/minute per-teacher limit remained enforced.

| Measurement                                   | Recorded result                                        |
| --------------------------------------------- | ------------------------------------------------------ |
| Cold web readiness                            | 143.18 seconds                                         |
| Batch admission response                      | 8.69 seconds                                           |
| First complete student visible                | 178.90 seconds after acceptance                        |
| Full batch complete                           | 589.91 seconds after acceptance — 9 minutes 50 seconds |
| Peak simultaneous provider calls              | 3                                                      |
| Sampled peak application memory               | 337.50 MiB                                             |
| Slowest sampled health request during grading | 0.73 seconds                                           |
| Whole-container restart web readiness         | 295.25 seconds                                         |
| Results preserved after restart               | 100 question grades and 200 criterion breakdowns       |
| Usage after restart                           | 110 successful calls, with no repeated calls           |
| Memory exhaustion                             | No OOM kill                                            |

The script observed 87 progress samples, checked that incomplete students exposed no partial grades, and observed a complete student while others remained active. Its acceptance criteria included finishing within 900 seconds after admission and sampled memory below 450 MiB. Admission includes creation of the batch snapshots and is visibly slower under the hard CPU limit.

These results exclude Neon network latency, Render scheduling and actual provider variability. The mounted test transport initializes Django before process entry, adding startup overhead. Peak memory and health latency are sampled observations, not exhaustive maxima. The fifteen-minute completion target is therefore a demo target, not a guarantee.

## Other recorded grading and startup timings

| Run                                         | Individual grading                | Batch grading                                    | Other observations                                                                                         |
| ------------------------------------------- | --------------------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| Earlier synchronous criterion-grading check | 16.8 seconds                      | 124.8 seconds with deliberately delayed calls    | 62 health checks stayed responsive; provider waits were outside transactions.                              |
| Later synchronous review/account check      | 17.2 seconds                      | 126.3 seconds with deliberately delayed calls    | 62 responsive health checks; 34 mocked provider waits, none inside a transaction.                          |
| Current asynchronous supervised smoke check | 18.54 seconds for three questions | 55.72 seconds for five students × five questions | First complete batch student at 27.89 seconds; 34 successful calls across the individual and batch checks. |
| Earlier constrained worker-startup check    | Not measured                      | Not measured                                     | About 330 seconds to cold web/worker readiness, about 212 MiB memory, no OOM at 0.1 CPU/512 MiB.           |

The asynchronous smoke check used 4.1-second simulated call delays and no CPU limit. Repeated action keys returned the original receipt without additional work. The older synchronous runs are retained as historical evidence; they are not timings for the current API. Workloads and delay conditions differ, so this table does not establish a controlled speedup ratio. The historical notes do not contain enough detail to reproduce every older run exactly.

A separate deployed login fetch took **23.39 seconds**. It is not a grading measurement or verified cold-start measurement. Controlled idle-wakeup timing and real-provider 10 × 10 timings have not been established.

## Crash and concurrency verification

Independent process checks exercise actual process termination and PostgreSQL connection termination. One check uses file-backed SQLite and local uploads. Lease-expiry tests accelerate expiry in disposable records.

| Boundary                                     | Verified behavior                                                            |
| -------------------------------------------- | ---------------------------------------------------------------------------- |
| Kill after saved mapping/question response   | Recover saved work without another provider call.                            |
| Kill during publication                      | Roll back the student's new results, then publish the complete saved result. |
| Kill after committed publication             | Preserve grades and avoid replaying AI.                                      |
| Kill after dispatch without a saved response | Require explicit possible-charge retry and retain the reservation.           |
| Drop PostgreSQL connection after dispatch    | Recover conservatively without silently resending.                           |
| Expire claim while old process remains alive | Successor finishes; old process cannot overwrite it.                         |
| Competing workers and quota reservations     | Enforce the global call limit and quota allowance.                           |
| Duplicate wake signals followed by idle      | Execute once, close DB connections and stop periodic idle DB scans.          |
| SQLite process death with an upload          | Preserve file/job/response and publish after recovery.                       |

An image check also verified maintenance `503` responses and readable owned history, followed by saved-response publication after container replacement with no provider credentials. A Docker Compose check preserved a SQLite account/upload and worker readiness across replacement. Current verification passed **284 PostgreSQL backend tests and 19 frontend tests**, plus lint/format, builds, schema validation and migration consistency. These are local checks; deployed service behavior must be verified separately.

Two earlier small live synthetic checks confirmed mark allocation (`3 + 7 = 10`, with a matching three-mark rubric) and criterion grading (a reversed explanation received `1/5` with feedback per criterion). They are functional examples, not a quality dataset or accuracy benchmark.

## Reproduce the current checks

Use the [source environment](SETUP.md#develop-from-source), quality dependencies and Docker. From the repository root, start a disposable database:

```sh
docker run --detach --name graider-capacity-postgres \
  --publish 127.0.0.1:55437:5432 \
  --env POSTGRES_USER=graider \
  --env POSTGRES_PASSWORD=ci-only-password \
  --env POSTGRES_DB=graider_verification postgres:18-alpine
docker exec graider-capacity-postgres pg_isready -U graider -d graider_verification
```

Wait until PostgreSQL reports ready. Build the frontend/assets and local image:

```sh
npm run build --prefix frontend
DJANGO_DEBUG=true DJANGO_SECRET_KEY=verification-only \
  DATABASE_URL=postgresql://graider:ci-only-password@127.0.0.1:55437/graider_verification \
  python backend/manage.py collectstatic --noinput
docker build --tag graider:verification .
```

Run process tests, constrained capacity, supervised grading and image recovery checks:

```sh
DJANGO_DEBUG=true DJANGO_SECRET_KEY=verification-only \
  DATABASE_URL=postgresql://graider:ci-only-password@127.0.0.1:55437/graider_verification \
  python backend/manage.py test apps.ai_jobs.test_processes --noinput

DATABASE_URL=postgresql://graider:ci-only-password@127.0.0.1:55437/graider_verification \
  python scripts/check_ai_job_capacity.py \
  --postgres-container graider-capacity-postgres \
  --image graider:verification --report /tmp/graider-capacity.json

DATABASE_URL=postgresql://graider:ci-only-password@127.0.0.1:55437/graider_verification \
  python scripts/production_smoke.py

DATABASE_URL=postgresql://graider:ci-only-password@127.0.0.1:55437/graider_verification \
  python scripts/check_ai_job_rollout.py \
  --postgres-container graider-capacity-postgres --image graider:verification
```

The three scripts reject remote DB addresses and create/remove their own temporary databases/processes/containers. Container checks remove their private networks. They leave the selected PostgreSQL container and report in place. Remove only this disposable server when finished:

```sh
docker rm --force --volumes graider-capacity-postgres
```

Process tests run in PostgreSQL CI. The slower constrained capacity check is run explicitly. Simulated transport/fault helpers live under `scripts/ai_jobs_verification/`, outside the production image, and are mounted only for checks. Reports contain counts/timings/image metadata rather than prompts, student data or credentials. Rerunning the current checkout can produce different timings from the preserved historical report.
