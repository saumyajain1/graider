# Grading benchmarks and recovery evidence

All workloads use synthetic submissions. Production measurements use real OpenAI calls; local capacity experiments use simulated responses. These are workload-specific observations, not grading-accuracy or latency guarantees.

## Production grading — October 6, 2026

**Ten students × ten questions completed in 113.50 seconds (1m 54s)** on Render's Free service, advertised at **0.1 CPU and 512 MB RAM**, with Neon PostgreSQL and real GPT-6 Luna calls. Each short arithmetic answer had a reference answer and two rubric criteria. Mapping used low reasoning; scoring used medium. The timer covers the first grading step through the final committed student result, including mapping, provider waits, validation and persistence. Assignment setup, authentication, admission, startup and restart are excluded.

| Measurement                      | Observed result                                                                                          |
| -------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Saved output                     | 100 question grades, 200 criterion breakdowns                                                            |
| Successful provider calls        | 10 mapping + 100 scoring; 71,342 tokens                                                                  |
| First complete student result    | 100.39s; available while other students were grading                                                     |
| Sampled peak container memory    | 313.76 MiB; zero added OOM kills                                                                         |
| Container CPU consumed           | 16.09 CPU-seconds across the grading interval                                                            |
| SDK call time, mapping           | Median 3.19s; p95 3.59s                                                                                  |
| SDK call time, scoring           | Median 2.18s; p95 2.90s; maximum 4.48s                                                                   |
| Job admission / progress polling | HTTP 202 in 1.89s; median progress request 0.66s, maximum 1.12s                                          |
| Publication integrity            | No partial student results observed                                                                      |
| Production restart               | All 100 grades, 200 criterion breakdowns and 110 successful usage records unchanged; no additional calls |

Settings: **10 call slots, 10 active students, one Gunicorn process/four threads, 2s scans, 120 requests/minute**. The trace observed at most six overlapping SDK calls; ten slots do not imply ten continuously executing calls. Token budgets were unchanged. At 60 requests/minute, an earlier live run paused; after deployment and explicit resume, all **84 saved successful calls were reused** and only the remaining 26 executed.

Timing and resources come from all **340 numeric log events**; usage and results were independently checked in Neon and progress through the authenticated API every five seconds. Memory is an event-sampled peak for the whole service, not continuous monitoring. CPU includes web and worker activity; Render's advertised shared allocation is not a verified strict CPU throttle. The live requests were faster than the local harness's fixed 8–10s delays, so this is not a controlled speedup comparison. Complex or longer answers can take longer. Full evidence: [ai-grading-production.json](ai-grading-production.json).

## Local grading measurements

On **October 6, 2026**, ten students × ten questions completed in **221.27 seconds (3m 41s)** with **301.6 MiB sampled peak memory**. The complete workload included ten answer-mapping calls, 100 question grades and 200 criterion breakdowns. The first student's complete result committed at **188.68 seconds** while other students were still grading.

The application was constrained to **0.1 CPU, 512 MiB RAM and no extra swap**, with PostgreSQL outside the container. Simulated responses took eight seconds, or ten seconds for one student. The timer covered worker release through the final publication commit; assignment preparation, login, admission, startup and restart were excluded. All grades and usage records were verified, with no partial student results or OOM kills.

| Complete grading, 10 concurrent calls/students | Scan | Observation                           | Time                 | Sampled peak RAM |
| ---------------------------------------------- | ---- | ------------------------------------- | -------------------- | ---------------- |
| Isolated run                                   | 1s   | HTTP progress/health polling          | 266.33s — 4m 26s     | 344.3 MiB        |
| Isolated run                                   | 2s   | HTTP progress/health polling          | 252.80s — 4m 13s     | 340.8 MiB        |
| Isolated run                                   | 2s   | External DB, no periodic web requests | **221.27s — 3m 41s** | **301.6 MiB**    |

### Concurrency comparison

These scoring-only runs prepared mapping checkpoints before timing the 100 question grades. AI delays and rubric size stayed fixed. Some initial sweep runs shared the host/database concurrently; confirmation runs were isolated. Warm-start runs used two CPUs for startup, then verified the 0.1-CPU limit before any timed work.

| AI calls / students               | Scoring-only time | Sampled peak RAM |
| --------------------------------- | ----------------- | ---------------- |
| 3 / 3, 2s scan                    | 456.30s — 7m 36s  | 355.0 MiB        |
| 6 / 6, 2s scan                    | 278.29s — 4m 38s  | 345.1 MiB        |
| 10 / 10, 2s scan                  | 201.39s — 3m 21s  | 348.7 MiB        |
| 10 / 10, isolated repeat, 1s scan | 239.61s — 4m 00s  | 340.5 MiB        |

The recommended configuration is **10 AI calls, 10 active students, one Gunicorn process/four threads, a two-second scan and 120 requests/minute**; token budgets remain unchanged. The initial sweep used 120 requests/minute to remove quota interference. At 40/minute, jobs paused and needed explicit retry. The 3m 02s best observation was not reproduced in isolation, and extra web processes had no clear advantage. Higher concurrency also delayed the first student: 127.00s at three students versus 151.99s in the fastest ten-student sweep.

All eleven reports, including the pilot, failures and timing boundaries, are preserved in [ai-grading-concurrency.json](ai-grading-concurrency.json). The 201.39s pilot used `finished_at`; later runs observed publication after commit. Local results exclude Neon network latency, Render scheduling and actual OpenAI variability.

## Earlier measurements

| Run / conditions                                                                | Grading timing                                                                    | Other evidence                                                                                          |
| ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| October 3 constrained 10 × 10, three concurrent students, simulated 8–10s calls | **589.91s — 9m 50s**, including 8.69s admission; first student visible at 178.90s | 337.50 MiB peak; slowest sampled health request 0.73s; web readiness 143.18s; restart readiness 295.25s |
| Earlier synchronous criterion grading, delayed simulated calls                  | Individual 16.8s; batch 124.8s                                                    | 62 responsive health checks; provider waits outside transactions                                        |
| Later synchronous review/account check, delayed simulated calls                 | Individual 17.2s; batch 126.3s                                                    | 62 responsive health checks; 34 provider waits outside transactions                                     |
| Asynchronous smoke, unconstrained CPU, simulated 4.1s calls                     | Three-question individual 18.54s; 5 × 5 batch 55.72s; first batch student 27.89s  | 34 successful calls; duplicate action keys reused the same job                                          |
| Earlier 0.1-CPU / 512-MiB startup check                                         | No grading measurement                                                            | About 330s readiness; about 212 MiB memory; no OOM                                                      |

The October 3 report is preserved in [ai-job-capacity.json](ai-job-capacity.json), with source `69917cf` and runtime image ID. Restart retained all **100 question grades, 200 criterion breakdowns and 110 successful usage records** without repeating provider calls. Startup, fixtures and restart were outside its grading timer. Different workloads and observation methods prevent a controlled speedup comparison with newer runs.

A deployed login fetch took 23.39s; this is neither a grading nor verified cold-start measurement. Earlier small live checks confirmed a 3 + 7 mark allocation and criterion feedback for a reversed explanation graded 1/5. These functional examples do not establish grading accuracy.

## Recovery verification

Local process tests use actual process termination and PostgreSQL connection termination. SQLite/upload persistence is checked separately; lease expiry is accelerated in disposable records.

| Failure boundary                                   | Verified behavior                                                         |
| -------------------------------------------------- | ------------------------------------------------------------------------- |
| Kill after a saved mapping/question response       | Resume without repeating the provider call                                |
| Kill during publication                            | Roll back partial results, then publish the complete saved student result |
| Kill after publication                             | Preserve grades without replaying AI                                      |
| Kill after dispatch, before saving a response      | Require acknowledgement of possible charges before retry                  |
| Drop a database connection after dispatch          | Recover without silently resending                                        |
| Expire a claim while the old process remains alive | Fence the old worker from overwriting its successor                       |
| Competing workers/quota reservations               | Respect global concurrency and token allowance                            |
| Duplicate wake signals, then idle                  | Execute once, close DB connections and stop idle scans                    |
| SQLite process death with an upload                | Preserve the file, job and saved response                                 |

Image maintenance/recovery and Docker Compose replacement checks also preserved local data and worker readiness. The earlier release passed **288 PostgreSQL backend tests and 19 frontend tests**, alongside lint, builds, schema and migration checks. These checks are separate from deployed benchmarking.

## Reproduction

Use the [source environment](SETUP.md#develop-from-source), Docker and a disposable local PostgreSQL server. Build the image, then run the selected grading configuration:

```sh
docker run --detach --name graider-capacity-postgres \
  --publish 127.0.0.1:55437:5432 --env POSTGRES_USER=graider \
  --env POSTGRES_PASSWORD=ci-only-password --env POSTGRES_DB=graider_verification postgres:18-alpine
docker exec graider-capacity-postgres pg_isready -U graider -d graider_verification
docker build --tag graider:verification .
DATABASE_URL=postgresql://graider:ci-only-password@127.0.0.1:55437/graider_verification \
  python scripts/check_ai_job_capacity.py \
  --postgres-container graider-capacity-postgres --image graider:verification \
  --grading-only --quiet-observation --warm-start --concurrency 10 \
  --student-concurrency 10 --scan-seconds 2 --requests-per-minute 60 \
  --report /tmp/graider-grading.json
```

Wait for PostgreSQL readiness before the check. Use `--scoring-only` to exclude mapping; omit `--quiet-observation` to include HTTP polling. Omit the timing-mode arguments for the older admission/restart capacity check. Other configurations are exposed by `--help`. The harness rejects remote databases, uses opt-in simulated transport outside the production image and removes its temporary databases/containers/networks. Remove the disposable PostgreSQL container afterwards.

Run `apps.ai_jobs.test_processes` through Django's test runner for crash checks; [production_smoke.py](../scripts/production_smoke.py) and [check_ai_job_rollout.py](../scripts/check_ai_job_rollout.py) cover supervised execution and image replacement. Those scripts also reject remote databases. Reports omit prompts, student data and credentials.

For an explicitly authorized **real-provider** deployed run, use [benchmark_live_grading.py](../scripts/benchmark_live_grading.py) with the service's environment file, HTTPS URL and `--allow-live-ai`. It prepares synthetic assignments, admits jobs through the authenticated API and observes progress every five seconds. Enable `GRAIDER_AI_METRICS` on the service to capture SDK request durations, committed-result timestamps and cgroup resource samples in numeric logs; timing records alone do not include exact commit boundaries. The script disables its synthetic account and preserves usage accounting so real charges continue to count against quotas.
