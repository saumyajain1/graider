# Graider V1 Design Overview

## Purpose

Graider is an AI-assisted grading MVP for teachers. It helps a teacher turn an assignment into structured grading artifacts, run an initial grading pass over student submissions, and review the results before finalizing marks.

The product is intentionally teacher-controlled:

1. Create an assignment from pasted text, `.txt`, or `.pdf`.
2. Build or generate question parts.
3. Create reference answers and rubric criteria.
4. Add student submissions manually, from uploaded files, or by CSV.
5. Run AI-assisted grading.
6. Review, edit, finalize, and export results.

AI output is never the final authority. Teachers can edit every important artifact before using it.

## Product Principles

- **Human in the loop:** AI proposes; the teacher decides.
- **Structured workflow:** grading artifacts are stored as data, not as chat transcripts.
- **Editable outputs:** questions, answers, rubric criteria, scores, and feedback remain teacher-editable.
- **Teacher-scoped data:** assignments and grading records are only accessible to their owner.
- **Simple MVP scope:** the system favors a clear end-to-end workflow over production-scale infrastructure.

## Current MVP Scope

### Included

- Teacher registration, login, logout, and session-protected routes
- Assignment creation from text, `.txt`, or `.pdf`
- Manual question editing plus AI-assisted question decomposition
- Reference-answer generation and editing
- Rubric generation and editing
- Manual, file, and CSV submission intake
- AI-assisted answer mapping and grading
- Teacher review of scores and feedback
- Finalization and CSV export

### Deliberately out of scope

- Student accounts or student-facing submission flows
- LMS integrations
- Multi-teacher collaboration
- Advanced analytics
- Background job infrastructure
- Production storage, deployment, and compliance hardening

## System Shape

### Frontend

- React
- TypeScript
- Vite
- Tailwind CSS
- React Router
- TanStack Query

The frontend is organized around the assignment workflow:

- dashboard
- assignment overview
- questions
- reference answers
- rubric
- submissions
- review

### Backend

- Django
- Django REST Framework
- SQLite for the current MVP
- OpenAI API integration
- Pydantic schemas for structured model outputs

The backend is split into three application areas:

- `accounts`: teacher authentication and identity
- `assignments`: assignment source text and question-part setup
- `grading`: generated artifacts, submissions, grading workflow, review, and export

LLM-facing work is kept behind service modules so request handlers stay focused on HTTP concerns and the model provider can be changed later without rewriting the rest of the app.

## Key Design Decisions

### Fixed workflow instead of autonomous agents

Graider uses a predictable grading pipeline rather than giving an agent open-ended control over grading. That keeps the workflow easier to test, easier to review, and easier for teachers to understand.

### Structured outputs instead of chat transcripts

Each AI task returns typed data that can be validated and stored. The system does not treat long freeform responses as the main artifact.

### Separate AI suggestions from teacher decisions

`GradingResult` keeps AI-generated scores and feedback separate from teacher-editable final scores and feedback. That preserves auditability inside the workflow and keeps human review explicit.

### Context parts are first-class data

`QuestionPart` supports both shared `context` blocks and graded `question` blocks. This lets multi-part questions preserve shared setup without duplicating that text into every graded answer.

### HTTP views stay thin

Submission import/export, grading orchestration, and LLM calls live in service modules. API views handle authentication, validation, and response shaping rather than absorbing all business logic.

### Teacher ownership is enforced at the API boundary

Assignment, artifact, submission, review, and export lookups are scoped to the authenticated teacher before data is returned or changed.

## Core Data Model

### `Assignment`

One teacher-owned grading project containing source text and workflow state.

### `QuestionPart`

An ordered assignment fragment. Parts may be either:

- `context`: shared setup text
- `question`: a graded question part

### `ReferenceAnswer`

The expected answer for one question part. It may be AI-generated or teacher-authored.

### `RubricCriterion`

One scoring criterion attached to a question part.

### `StudentSubmission`

A student's submitted work, including ingestion source, grading status, and final total.

### `SubmissionAnswerPart`

The portion of a student's response mapped to one question part.

### `GradingResult`

The AI score, teacher-adjustable final score, feedback, reasoning summary, and review flag for one submission/question pair.

## Workflow

### Assignment Setup

1. The teacher creates an assignment and provides source text.
2. Graider normalizes text from manual input or supported uploads.
3. The teacher either creates question parts manually or generates them with AI.
4. The teacher reviews and edits question structure.
5. Graider generates reference answers and rubric criteria.
6. The teacher edits those artifacts as needed.

### Grading

1. The teacher adds submissions manually, from files, or by CSV.
2. Graider maps each response to the assignment's question parts.
3. Each answer part is graded against the question, reference answer, and rubric.
4. The teacher reviews AI scores and feedback, adjusts them if needed, and finalizes results.
5. Final results can be exported as CSV.

## Grading Process

### 1. Question decomposition

- Input: raw assignment text
- Output: ordered `QuestionPart` records, including shared context when relevant
- Teacher control: generated parts can be edited, reordered, or replaced manually

### 2. Reference-answer generation

- Input: question text, shared context, and available mark information
- Output: one editable `ReferenceAnswer` per graded question part

### 3. Rubric generation

- Input: question text, shared context, reference answer, and max marks
- Output: editable `RubricCriterion` records for that question part

### 4. Submission answer mapping

- Input: a student's full response and the assignment's question parts
- Output: `SubmissionAnswerPart` records that associate answer text with each question part

### 5. First-pass grading

- Input: mapped answer text, question part, reference answer, and rubric criteria
- Output: `GradingResult` records with AI score, feedback, reasoning summary, confidence, and review flag

### 6. Teacher review and finalization

- The teacher reviews the AI output, adjusts final scores or feedback, and finalizes the submission.
- Export uses final teacher-reviewed values when they exist.

## AI Integration

Graider uses structured model outputs for:

- question decomposition
- reference-answer generation
- rubric generation
- answer mapping
- grading

The current MVP uses the same configured OpenAI model family across these tasks and validates outputs before saving them. The application also keeps manual editing available when AI generation is unavailable or produces something that needs correction.

## API Surface

The backend exposes a REST API under `/api`.

### Authentication

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/register` | Create a teacher account |
| `POST` | `/api/auth/login` | Start a teacher session |
| `POST` | `/api/auth/logout` | End the current session |
| `GET` | `/api/auth/me` | Return the current teacher |

### Assignments and question parts

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/assignments/` | List the teacher's assignments |
| `POST` | `/api/assignments/` | Create an assignment |
| `GET` | `/api/assignments/:assignmentId` | Fetch one assignment |
| `PATCH` | `/api/assignments/:assignmentId` | Update an assignment |
| `DELETE` | `/api/assignments/:assignmentId` | Delete an assignment |
| `GET` | `/api/assignments/:assignmentId/questions` | List question parts |
| `POST` | `/api/assignments/:assignmentId/questions` | Create a question part |
| `POST` | `/api/assignments/:assignmentId/questions/generate` | Generate question parts |
| `POST` | `/api/assignments/:assignmentId/questions/reorder` | Reorder question parts |
| `PATCH` | `/api/assignments/questions/:questionId` | Update a question part |
| `DELETE` | `/api/assignments/questions/:questionId` | Delete a question part |

### Reference answers and rubric

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/assignments/:assignmentId/reference-answers` | List reference answers |
| `POST` | `/api/assignments/:assignmentId/reference-answers` | Create a manual reference answer |
| `POST` | `/api/assignments/:assignmentId/reference-answers/generate` | Generate reference answers |
| `PATCH` | `/api/reference-answers/:referenceAnswerId` | Update a reference answer |
| `GET` | `/api/assignments/:assignmentId/rubric` | List rubric groups |
| `POST` | `/api/assignments/:assignmentId/rubric` | Create a rubric criterion |
| `POST` | `/api/assignments/:assignmentId/rubric/generate` | Generate rubric criteria |
| `PATCH` | `/api/rubric-criteria/:criterionId` | Update a rubric criterion |
| `DELETE` | `/api/rubric-criteria/:criterionId` | Delete a rubric criterion |

### Submissions, grading, and export

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/assignments/:assignmentId/submissions` | List submissions |
| `POST` | `/api/assignments/:assignmentId/submissions` | Create a submission |
| `POST` | `/api/assignments/:assignmentId/submissions/import-csv` | Import submissions from CSV |
| `GET` | `/api/submissions/:submissionId` | Fetch one submission |
| `POST` | `/api/submissions/:submissionId/grade` | Grade one submission |
| `POST` | `/api/assignments/:assignmentId/grade-all` | Grade all submissions |
| `GET` | `/api/submissions/:submissionId/grading` | Fetch nested grading detail |
| `PATCH` | `/api/grading-results/:gradingResultId` | Save teacher review changes |
| `POST` | `/api/submissions/:submissionId/finalize` | Finalize one submission |
| `GET` | `/api/assignments/:assignmentId/export.csv` | Export final results |

## Security and Privacy Boundaries

- Every API workflow is scoped to the authenticated teacher.
- API keys remain server-side.
- Student data is not exposed across teacher accounts.
- Uploaded files and local development data are excluded from source control.

These safeguards are part of the MVP, but the project is still not presented as a production-ready grading platform.

## Current Limitations

- SQLite and local media storage are appropriate for the MVP, not for production deployment.
- AI calls currently run synchronously.
- The project does not yet include OAuth2/OIDC, background jobs, managed storage, deployment automation, or observability tooling.
- The review flow is designed for teacher oversight, not fully automated grading.

## Summary

Graider V1 demonstrates a complete teacher-facing grading workflow:

- ingest assignment text
- structure questions
- create grading artifacts
- grade submissions
- review and export results

The architecture keeps the workflow understandable, the data model explicit, and AI output subordinate to teacher review. That makes the MVP useful as a working product demo while leaving clear paths for future production hardening.
