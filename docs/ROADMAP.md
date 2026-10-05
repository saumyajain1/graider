# Issues, features and improvements

This roadmap records unresolved limitations and proposed features for the current checkout. Listed changes are not yet implemented; priorities can change as the demo evolves.

## User experience

| Issue                            | Current limitation                                                                                                                                | Proposed improvement                                                                                                                         |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Stale published grades           | Published grades are not marked when questions, reference answers or rubrics change. Saved scoring inputs can differ from the current assignment. | Track input versions, identify affected submissions and offer explicit regrading while preserving teacher overrides where compatible.        |
| Export scope                     | CSV export includes all submission statuses without a choice between all submissions and finalized results.                                       | Offer export scope, show unfinished counts and label incomplete totals clearly.                                                              |
| Mobile navigation                | Workflow navigation takes much of the first screen at narrow widths.                                                                              | Add an expandable drawer while keeping all workflow steps discoverable.                                                                      |
| Stale file-input labels          | Native file selectors can display the previous filename after a successful create or import.                                                      | Clear selectors after success and retain the selection after failure.                                                                        |
| Save feedback and keyboard focus | Save feedback varies between editors; route changes do not explicitly manage heading focus or scroll.                                             | Standardize save/error announcements and route focus/scroll behavior; verify keyboard and screen-reader use.                                 |
| Duplicate question numbers       | Displayed question numbers can duplicate, making CSV headers ambiguous.                                                                           | Warn about duplicate scored-question labels, offer renumbering and make export headers unambiguous without forbidding shared-context labels. |
| Browser draft loss               | Unsaved drafts remain in memory and cannot survive a browser restart.                                                                             | Consider local/session draft persistence with privacy and multi-tab behavior accounted for.                                                  |

## OpenAI integrations

### Switch from Chat Completions to Responses

Migrate the shared AI client to OpenAI's recommended interface for new development. Preserve structured results, task models/reasoning, output limits, usage accounting and recovery; verify refusals and incomplete results. Existing API keys work without special approval. The migration enables future tool integrations but does not by itself establish better grading quality or performance.

### Sign in with ChatGPT

Add registration/sign-in alongside Google and passwords using OpenID Connect and explicit account linking. This authenticates the teacher without authorizing AI usage. Production website access currently requires an approved OpenAI client through its limited partner trial/waitlist.

### Use each teacher's ChatGPT plan or OpenAI API key

Add a billing choice for grading and other AI actions, protected per-teacher credentials and account-specific model/usage handling. Never silently charge the project owner when a teacher's connection fails. API keys require the teacher's API billing without special integration approval. ChatGPT-plan usage needs separate consent, token renewal and Responses streaming; the shared Render website requires OpenAI access approval. The documented local personal/open-source flow can be demonstrated without hosted-app approval.

References: [Responses migration](https://developers.openai.com/api/docs/guides/migrate-to-responses), [website sign-in](https://developers.openai.com/siwc/website), [ChatGPT-plan access](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt) and [plan inference requirements](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference).

## AI quality

| Limitation                                | Proposed improvement                                                                                                                                                                 |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Prompt injection                          | Delimit untrusted assignment/submission text, strengthen instruction/data separation and add adversarial tests. Schema and score checks alone do not establish injection resistance. |
| Incomplete output checks                  | Add semantic/format validation and review flags for suspicious instruction-following or unsuitable feedback.                                                                         |
| No systematic grading-quality measurement | Build a versioned human-scored dataset and evaluate answer mapping, score disagreement, rubric adherence and model/prompt regressions.                                               |
| Uncalibrated confidence                   | Calibrate model-reported confidence against human disagreement and choose review thresholds from evidence.                                                                           |
| No systematic prompt/model comparison     | Tie prompt-policy versions to evaluations and published-result metadata, and compare quality before changing defaults.                                                               |
| Unbenchmarked model routing               | Compare task-specific cost, latency and quality; add controlled fallback only when justified.                                                                                        |
| Limited long-document support             | Add chunking/context selection if measured large-document needs exceed current input limits.                                                                                         |
| Limited observability and edit history    | Add privacy-safe latency/error/usage summaries and a revision trail for AI suggestions versus teacher changes.                                                                       |
| Untested bias and consistency             | Evaluate anonymized and counterfactual cases for irrelevant name/order effects and strengthen human-review rules.                                                                    |

## Other integrations

| Feature            | Proposed scope                                                                                                                                                          |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GitHub sign-in     | Add another identity provider if there is a concrete user need.                                                                                                         |
| Canvas integration | Explore institution-specific OAuth registration and authorization for login, assignment import and result export. Existing Google sign-in does not grant Canvas access. |

## Operations

| Limitation                                        | Proposed improvement                                                                                                                                          |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Shared small web/worker service                   | For higher traffic, separate worker/web capacity and revisit the coordinator lock and queue design.                                                           |
| Service sleep and slow startup                    | Use always-on compute if unattended completion or predictable startup becomes required. No jobs execute while the service is stopped.                         |
| Completion time is not guaranteed                 | Measure real-provider and deployed wake/network behavior before setting a latency promise; current capacity timings use simulated calls and local PostgreSQL. |
| Possible duplicate provider charges after a crash | Retain explicit acknowledgement for uncertain retries and investigate provider-supported reconciliation. External exactly-once execution is not guaranteed.   |
| Shared AI allowance can be exhausted              | Consider optional controlled demo access if quotas and the provider cap do not provide sufficient availability for visitors.                                  |
| Production password-recovery email                | Configure verified Brevo credentials and test delivery before relying on password recovery. Email-provider setup remains deferred.                            |
| Manual job-history cleanup                        | Add a retention schedule that preserves active work and usage accounting and suits the hosting lifecycle.                                                     |
