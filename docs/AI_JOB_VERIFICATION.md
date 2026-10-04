# Background job verification

Benchmark run: **2026-10-03**, America/Vancouver.

Step 4 verifies the worker implemented in steps 1–3. It changes tests and verification tools; production code, schema and env defaults remain unchanged. Background job mode remains disabled pending step 5 and owner-approved rollout.

## Crash and concurrency tests

The backend suite includes eleven new tests. Ten launch independent Python processes against Django's disposable PostgreSQL test database; one uses a file-backed SQLite database and local upload directory.

| Boundary                                           | Required result                                                                                         |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Kill after a saved mapping or question response    | Recover the saved response/checkpoint without another provider call.                                    |
| Kill during publication                            | Roll back every new result for that student; later publish the complete result without repeating AI.    |
| Kill after committed publication                   | Preserve results and avoid repeating AI on restart.                                                     |
| Kill after dispatch, before a saved response       | Pause for explicit retry with acknowledgement of a possible prior charge; retain the usage reservation. |
| Terminate the PostgreSQL connection after dispatch | Recover safely without silently dispatching the same request again.                                     |
| Expire a claim while its old process remains alive | A successor can finish; the old process cannot overwrite its work.                                      |
| Competing worker processes                         | Enforce the global three-call limit and prevent overlapping quota reservations exceeding the allowance. |
| Repeated wake signals, then idle                   | Execute once, close database connections and stop periodic queue scans while idle.                      |
| Restart with SQLite and a local upload             | Preserve the file, job, saved response and published answer across process death.                       |

Faults use actual process termination and PostgreSQL connection termination. The tests accelerate lease expiry by updating the disposable test records. Provider replies use the real OpenAI SDK through a test-only HTTP transport; no external AI request is made. Existing tests cover ownership, draft protection, cancellation, input changes, scheduling, safe retries and API/UI contracts.

The full PostgreSQL backend suite passed **274 tests**. The idle check was strengthened afterward and passed separately.

## Constrained container workload

`scripts/check_ai_job_capacity.py` runs the production image with **0.1 CPU, 512 MiB RAM and no extra swap allowance**. The image runs its normal supervisor, Gunicorn and background worker. The benchmark signs in through the API with session/CSRF checks, admits a batch, polls progress and fetches published student results.

The fixture contains ten students, ten questions per student and two criteria per question. Each student needs one mapping call and ten grading calls: **110 provider calls, 100 question results and 200 criterion results**. Calls have an eight-second simulated delay; one student uses ten seconds per call. Global call and student concurrency are both three. The normal 40 requests/minute and token allowance defaults remain enforced.

The benchmark checks that admission returns promptly, no unfinished student exposes partial grades, a complete student is available while others run, the full batch finishes within 900 seconds after acceptance, sampled memory remains below 450 MiB and the container is not killed for exceeding memory. It then restarts the entire container and verifies persisted jobs/results/session access without repeated AI calls.

The local run completed successfully using the production runtime from `69917cf`. The machine-readable [report](ai-job-capacity.json) records the image ID.

| Measurement                                   | Result                                                 |
| --------------------------------------------- | ------------------------------------------------------ |
| Cold web readiness                            | 143.18 seconds                                         |
| Batch admission response                      | 8.69 seconds                                           |
| First complete student visible                | 178.90 seconds after acceptance                        |
| Full 10 × 10 batch                            | 589.91 seconds (9 minutes 50 seconds) after acceptance |
| Peak simultaneous provider calls              | 3                                                      |
| Sampled peak application memory               | 337.50 MiB                                             |
| Slowest sampled health request during grading | 0.73 seconds                                           |
| Restart web readiness                         | 295.25 seconds                                         |
| Persisted output                              | 100 question grades and 200 criterion breakdowns       |
| Provider accounting after restart             | 110 successful calls; no repeated calls                |
| Memory exhaustion                             | No OOM kill                                            |

The 8.69-second admission time is measured under the hard CPU limit and includes creating the entire batch's input snapshots. It is separate from the background grading time. Cold startup and restart are visibly slow under this CPU allowance.

These measurements use synthetic prompts and a local PostgreSQL server outside the constrained application container. They do not measure model quality, real model latency, Neon network latency or Render's host scheduling/sleep behavior. Cold startup is measured separately from accepted-job processing. The mounted mock transport initializes Django before process entry, adding verification overhead to startup. The fifteen-minute target therefore remains a demo target rather than a production guarantee.

## Reproduce

Use a disposable local PostgreSQL container and an installed repository environment. The password below is only for this local test server; do not substitute the production database.

```sh
docker run --detach --name graider-capacity-postgres \
  --publish 127.0.0.1:55437:5432 \
  --env POSTGRES_USER=graider \
  --env POSTGRES_PASSWORD=ci-only-password \
  --env POSTGRES_DB=graider_verification postgres:18-alpine
docker exec graider-capacity-postgres pg_isready -U graider -d graider_verification
```

Wait for the database to report ready, then run from the repository root:

```sh
DJANGO_DEBUG=true DJANGO_SECRET_KEY=verification-only \
  DATABASE_URL=postgresql://graider:ci-only-password@127.0.0.1:55437/graider_verification \
  .venv/bin/python backend/manage.py test apps.ai_jobs.test_processes --noinput

docker build --tag graider:step4-review .
DATABASE_URL=postgresql://graider:ci-only-password@127.0.0.1:55437/graider_verification \
  .venv/bin/python scripts/check_ai_job_capacity.py \
  --postgres-container graider-capacity-postgres \
  --image graider:step4-review --report /tmp/graider-capacity.json
```

The script rejects remote database addresses and creates/removes its own temporary database, Docker network and application container. It leaves the selected PostgreSQL container and report in place. Remove the disposable server when finished:

```sh
docker rm --force --volumes graider-capacity-postgres
```

Process tests run automatically in the existing PostgreSQL CI suite. The slower constrained benchmark is an explicit local verification command. Its transport and fault helpers live under `scripts/ai_jobs_verification/`, outside the production image, and are mounted only for verification. Reports contain synthetic counts/timings and image metadata, without prompts, student data or credentials.
