# Graider V1 Design Document

## MVP Implementation Notes
The shipped MVP keeps the original product flow but makes a few explicit simplifications:

- SQLite is used instead of Postgres.
- All AI calls are synchronous; there is no Celery, Redis, or background job queue.
- Student submissions are supported through manual entry and CSV import only.
- The current implementation uses `gpt-5.4-mini` for question generation, artifact generation, answer mapping, and grading.
- The review flow supports teacher-edited final scores and feedback plus CSV export.
- Analytics, LMS integrations, advanced versioning, and multi-user collaboration remain out of scope for V1.

## 1. Overview
Graider is an AI-assisted grading application for instructors and TAs. It helps a teacher upload an assignment and a set of student submissions, generate structured grading artifacts using an LLM, run an initial automated grading pass, and then review and edit the results before finalizing marks.

V1 is intentionally an MVP. The goal is not to build a production-ready LMS integration platform. The goal is to build a clear, working demonstration of the core grading workflow:

1. Teacher logs in.
2. Teacher creates an assignment.
3. Teacher uploads assignment questions.
4. Graider generates structured question parts.
5. Graider generates reference answers.
6. Graider generates a rubric.
7. Teacher uploads student responses.
8. Graider grades student responses.
9. Teacher reviews and edits grades and feedback.
10. Teacher exports or copies final results.

The product should preserve the spirit of the original Graider project:
- purple visual identity
- sidebar/tab-driven workflow
- human-in-the-loop grading
- question-by-question grading artifacts
- editable AI-generated outputs

## 2. V1 Goals

### Primary goals
- Demonstrate a complete end-to-end AI-assisted grading workflow.
- Preserve the original product idea and UI feel while rebuilding on a stronger stack.
- Make the system reliable enough for demos and portfolio use.
- Keep the implementation simple and understandable.
- Show clear use of LLMs in a structured educational workflow rather than as a chatbot.

### Secondary goals
- Make it easy to extend in V2.
- Keep the architecture modular enough to swap models or providers later.
- Provide enough persistence and structure that the app feels like a real product, not a script demo.

### Non-goals for V1
- No Canvas integration.
- No Google Classroom or LMS integration.
- No student-facing portal.
- No multi-teacher collaboration.
- No advanced analytics dashboard.
- No plagiarism detection.
- No OCR-heavy document understanding pipeline.
- No agent-based orchestration.
- No real-time collaborative editing.
- No complex role/permission system beyond teacher auth.

## 3. Product Scope

### V1 users
Only one user type exists in V1:
- **Teacher / grader**

The teacher is responsible for uploading both:
- the assignment questions
- the student answers

### Core V1 use case
A teacher wants help grading a written assignment more efficiently. They provide the assignment text and student responses, let the system generate grading artifacts, run an AI-assisted first pass, and then review the results before finalizing.

## 4. Core Product Features

### 4.1 Authentication
- Teacher login
- Teacher logout
- Simple account model
- Only authenticated teachers can access assignments and grading workflows

V1 can use:
- email + password auth
- no social login
- no password reset flow unless easy to add later

### 4.2 Assignment creation
Teacher can:
- create a new assignment
- give it a title
- optionally add course name and short description
- paste or upload assignment content

Supported V1 assignment input:
- pasted plain text
- uploaded `.txt` or `.pdf`

For V1, if PDF parsing is messy, the UI should allow the teacher to manually edit the extracted text before proceeding.

### 4.3 Question decomposition
The system converts raw assignment text into structured question parts.

Outputs:
- question list
- optional question context blocks
- marks per question part if detectable
- display order

Teacher can:
- review generated question parts
- edit text
- edit marks
- add/delete/reorder parts manually

### 4.4 Reference answer generation
For each question part, the system generates a model/reference answer.

Teacher can:
- view generated answer
- edit answer manually
- regenerate answer for a question part

This is one of the higher-intelligence, low-frequency tasks.

### 4.5 Rubric generation
For each question part, the system generates rubric criteria and a max score.

Teacher can:
- view rubric criteria
- edit descriptions
- edit point allocation
- add/remove criteria manually

This is also a higher-intelligence, low-frequency task.

### 4.6 Student submission upload
Teacher uploads student responses.

Supported V1 formats:
- one text response per student entered manually
- CSV upload with columns like `student_name`, `student_id`, `response_text`
- optional `.txt` files if easy

V1 assumption:
- submissions are uploaded by the teacher
- no student account system
- no direct file submission from students

### 4.7 AI-assisted grading
For each student response, the system:
- maps response text to question parts
- evaluates each part against the rubric and reference answer
- generates criterion-level reasoning where useful
- generates marks per question part
- generates short feedback
- computes a total score

The output should be structured and reviewable, not just a freeform paragraph.

### 4.8 Review and editing
Teacher can review grading results in two levels:

#### Assignment-level view
- list of students
- grading status
- total score
- needs-review flags

#### Student-level review
- full submission text
- question-by-question grading
- awarded marks vs max marks
- feedback per part
- editable final score per part
- editable final feedback
- override support

### 4.9 Finalization / export
Teacher can:
- mark grading as finalized for a student
- export a CSV with student names, IDs, total marks, and optional feedback summary

## 5. Product Principles
- **Human in the loop:** AI suggests, teacher decides.
- **Structured over chatty:** outputs should be shaped as data, not long prose.
- **Editable everything:** teacher can revise question parts, answers, rubric, and grading.
- **Deterministic workflow:** a fixed grading pipeline, not autonomous agent behavior.
- **Simple but real:** enough persistence, auth, and UI polish to feel like a genuine application.

## 6. Tech Stack

### Frontend
- **React**
- **TypeScript**
- **Vite** for frontend tooling
- **Tailwind CSS** for styling
- **React Router** for routing
- **TanStack Query** for API state fetching/mutations

### Backend
- **Python**
- **Django**
- **Django REST Framework** for API endpoints
- **Celery** for background jobs (recommended even in V1 if manageable)
- **Redis** as Celery broker/result backend

If Celery feels too heavy during implementation, V1 can temporarily do synchronous jobs for smaller inputs, but the intended design should still assume background task support.

### Database
- **PostgreSQL**

Why PostgreSQL:
- reliable and standard for Django apps
- strong support for relational data
- easy handling of structured entities like assignments, question parts, rubric items, submissions, and grading results
- JSON fields available for flexible metadata when needed

### LLM
- **OpenAI API**
- **gpt-5.4** for high-intelligence, low-frequency tasks:
  - reference answer generation
  - rubric generation
  - difficult fallback evaluation
- **gpt-5.4-mini** for recurring tasks:
  - question decomposition in most cases
  - submission parsing/mapping
  - first-pass grading
  - feedback drafting

### Storage
- Local media storage for V1 is acceptable
- Later can move to S3-compatible storage

### Validation / schemas
- **Pydantic** for validating structured LLM outputs before saving them

### Authentication
- Django auth system
- token/session auth depending on frontend integration choice
- session-based auth is fine for V1 if frontend and backend are hosted together or proxied simply

## 7. Why this stack
This stack is chosen to optimize for:
- simple implementation
- strong Python ecosystem
- clean separation between frontend and backend
- good support for relational grading data
- easy portfolio presentation
- ability to grow later without rewriting everything again

It is much more maintainable than the original Reflex monolith and much more appropriate for a product with multiple editable entities and review workflows.

## 8. High-Level System Architecture

### Main layers
1. **React frontend**
   - teacher interface
   - forms, tables, review pages, status indicators

2. **Django API backend**
   - business logic
   - auth
   - persistence
   - LLM orchestration
   - export logic

3. **PostgreSQL database**
   - source of truth for all grading entities

4. **Background job layer**
   - long-running LLM operations
   - question generation
   - rubric generation
   - bulk grading

5. **OpenAI integration layer**
   - typed LLM service calls
   - structured output parsing
   - retry/error handling

## 9. High-Level Code Structure

## Backend structure
A suggested Django project layout:

```text
backend/
  manage.py
  config/
    settings.py
    urls.py
    celery.py
  apps/
    accounts/
      models.py
      serializers.py
      views.py
      urls.py
    assignments/
      models.py
      serializers.py
      views.py
      urls.py
    submissions/
      models.py
      serializers.py
      views.py
      urls.py
    grading/
      models.py
      serializers.py
      views.py
      urls.py
    llm/
      services/
        openai_client.py
        question_decomposer.py
        reference_answer_generator.py
        rubric_generator.py
        answer_mapper.py
        grader.py
      schemas/
        question_schema.py
        rubric_schema.py
        grading_schema.py
      prompts/
        question_prompts.py
        rubric_prompts.py
        grading_prompts.py
    exports/
      services/
        csv_exporter.py
    common/
      utils/
      exceptions/
      constants/
      mixins/
```

### Frontend structure
```text
frontend/
  src/
    app/
      router.tsx
      providers.tsx
    components/
      layout/
      common/
      forms/
      tables/
      grading/
    pages/
      LoginPage.tsx
      DashboardPage.tsx
      AssignmentCreatePage.tsx
      AssignmentQuestionsPage.tsx
      AssignmentReferenceAnswersPage.tsx
      AssignmentRubricPage.tsx
      AssignmentSubmissionsPage.tsx
      AssignmentGradingPage.tsx
      StudentReviewPage.tsx
    api/
      client.ts
      auth.ts
      assignments.ts
      submissions.ts
      grading.ts
    types/
      assignment.ts
      rubric.ts
      grading.ts
    hooks/
      useAssignment.ts
      useGradingJobs.ts
    styles/
```

## 10. Main Data Entities

### 10.1 TeacherUser
Represents the authenticated teacher.

Fields:
- id
- email
- password hash
- full_name
- created_at
- updated_at

### 10.2 Assignment
Represents one assignment/grading project.

Fields:
- id
- teacher_id
- title
- course_name
- description
- raw_assignment_text
- source_file
- status
- created_at
- updated_at

Possible statuses:
- draft
- questions_ready
- reference_answers_ready
- rubric_ready
- submissions_uploaded
- grading_in_progress
- review_ready
- finalized

### 10.3 QuestionPart
Represents a structured question fragment.

Fields:
- id
- assignment_id
- part_key
- parent_key_nullable
- part_type (`context` or `question`)
- text
- max_marks
- display_order
- created_by_ai
- created_at
- updated_at

### 10.4 ReferenceAnswer
Represents the model answer for a question part.

Fields:
- id
- question_part_id
- answer_text
- version
- source (`ai` or `teacher`)
- created_at
- updated_at

### 10.5 RubricCriterion
Represents one criterion under a question part.

Fields:
- id
- question_part_id
- title
- description
- max_points
- display_order
- created_by_ai
- created_at
- updated_at

### 10.6 StudentSubmission
Represents one student’s full submission.

Fields:
- id
- assignment_id
- student_name
- student_identifier
- raw_response_text
- upload_source
- grading_status
- total_score_nullable
- created_at
- updated_at

Possible grading statuses:
- pending
- grading
- graded
- reviewed
- finalized
- failed

### 10.7 SubmissionAnswerPart
Represents the mapped answer for one question part within a student submission.

Fields:
- id
- submission_id
- question_part_id
- extracted_answer_text
- mapping_confidence_nullable
- created_at
- updated_at

### 10.8 GradingResult
Represents the AI grading output for a submission/question pair.

Fields:
- id
- submission_id
- question_part_id
- ai_score
- final_score
- max_score
- ai_feedback
- final_feedback
- reasoning_summary
- confidence_score_nullable
- needs_review
- created_at
- updated_at

### 10.9 CriterionEvaluation (optional in V1)
If implemented, stores criterion-level grading.

Fields:
- id
- grading_result_id
- rubric_criterion_id
- ai_points_awarded
- final_points_awarded
- notes

This can be simplified away in V1 if needed, but is nice if feasible.

### 10.10 LLMJob
Tracks background LLM tasks.

Fields:
- id
- assignment_id nullable
- submission_id nullable
- job_type
- status
- started_at
- completed_at
- error_message
- metadata_json

Job types:
- decompose_questions
- generate_reference_answers
- generate_rubric
- grade_submission
- grade_all_submissions

## 11. High-Level Workflow

### 11.1 Assignment setup flow
1. Teacher creates assignment.
2. Teacher pastes or uploads assignment text.
3. System extracts/stores raw assignment text.
4. Teacher clicks **Generate Questions**.
5. System generates structured question parts.
6. Teacher reviews/edits question parts.
7. Teacher clicks **Generate Reference Answers**.
8. System generates reference answers for each question part.
9. Teacher reviews/edits answers.
10. Teacher clicks **Generate Rubric**.
11. System generates rubric criteria per question part.
12. Teacher reviews/edits rubric.

At this point the assignment is ready for submissions.

### 11.2 Submission + grading flow
1. Teacher uploads or pastes student submissions.
2. System stores each submission.
3. Teacher clicks **Grade All** or grades individually.
4. For each submission:
   - map text to question parts
   - evaluate answers against reference answer + rubric
   - generate marks and feedback
   - compute total score
   - flag low-confidence cases
5. Teacher reviews results.
6. Teacher edits marks/feedback if needed.
7. Teacher finalizes results.
8. Teacher exports CSV.

## 12. Detailed Grading Process

### Step 1: Question decomposition
Input:
- raw assignment text

Output:
- ordered question parts with marks and types

Model:
- usually `gpt-5.4-mini`
- escalate manually or in future to stronger model if parsing is poor

### Step 2: Reference answer generation
Input:
- question part text
- any surrounding context
- max marks if available

Output:
- concise but sufficiently complete reference answer

Model:
- `gpt-5.4`

### Step 3: Rubric generation
Input:
- question part text
- reference answer
- max marks

Output:
- criterion list with point distribution

Model:
- `gpt-5.4`

### Step 4: Submission answer mapping
Input:
- full student response
- question parts

Output:
- extracted or mapped text for each question part

Model:
- `gpt-5.4-mini`

### Step 5: First-pass grading
Input:
- question part
- reference answer
- rubric criteria
- mapped student answer

Output:
- ai_score
- feedback
- reasoning summary
- optional confidence / review flag

Model:
- `gpt-5.4-mini`

### Step 6: Optional fallback grading
Only used when:
- low confidence
- malformed output
- suspiciously inconsistent result
- teacher requests re-evaluation

Model:
- `gpt-5.4`

### Step 7: Human review
Teacher can:
- adjust scores
- edit feedback
- override AI outputs
- finalize

## 13. LLM Design Principles
- Use direct API calls, not agents.
- Use structured outputs for every major generation/grading step.
- Validate all outputs with Pydantic before saving.
- Persist both parsed outputs and raw model responses for debugging if desired.
- Keep prompts task-specific and narrow.
- Prefer deterministic, typed workflows over conversational prompting.

## 14. Suggested API Surface

### Auth
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`

### Assignments
- `GET /api/assignments`
- `POST /api/assignments`
- `GET /api/assignments/:id`
- `PATCH /api/assignments/:id`

### Question parts
- `GET /api/assignments/:id/questions`
- `POST /api/assignments/:id/questions/generate`
- `PATCH /api/questions/:id`
- `POST /api/assignments/:id/questions/reorder`

### Reference answers
- `GET /api/assignments/:id/reference-answers`
- `POST /api/assignments/:id/reference-answers/generate`
- `PATCH /api/reference-answers/:id`

### Rubric
- `GET /api/assignments/:id/rubric`
- `POST /api/assignments/:id/rubric/generate`
- `PATCH /api/rubric-criteria/:id`

### Submissions
- `GET /api/assignments/:id/submissions`
- `POST /api/assignments/:id/submissions`
- `GET /api/submissions/:id`

### Grading
- `POST /api/assignments/:id/grade-all`
- `POST /api/submissions/:id/grade`
- `GET /api/submissions/:id/grading`
- `PATCH /api/grading-results/:id`
- `POST /api/submissions/:id/finalize`

### Jobs
- `GET /api/jobs/:id`

### Export
- `GET /api/assignments/:id/export.csv`

## 15. Frontend UX / Visual Design

## Overall feel
The UI should retain the visual spirit of the old Graider:
- rich purple background or purple-tinted shell
- left sidebar navigation
- dark-ish or deep-indigo/purple accents
- clean cards/panels over the background
- tabs/sections corresponding to the grading workflow

The design should feel like a polished academic productivity tool.

### Core layout
- **Left sidebar** with app name/logo and workflow navigation
- **Main content area** with page title, status badges, actions, and editable content panels
- **Top bar** with teacher name, assignment selector, and logout

### Sidebar items
Suggested sidebar structure:
- Dashboard
- Assignments
- Questions
- Reference Answers
- Rubric
- Submissions
- Grading Review
- Settings (optional/light)

Within a single assignment, these can also appear as step tabs:
- Overview
- Questions
- Reference Answers
- Rubric
- Submissions
- Review

### Visual style notes
- Purple gradient or purple primary background
- Light cards with subtle shadows on top of the purple shell
- Rounded corners
- Clear status chips such as Draft, Grading, Review Ready
- Tables for submissions
- Accordion/cards for question-by-question review
- Textareas for editable AI outputs

### Important UI principle
The app should feel structured and workflow-oriented, not chat-oriented.
Every page should answer: what stage of grading am I in, what did AI generate, and what can I edit?

## 16. Main Frontend Screens

### 16.1 Login page
Simple teacher login form.

### 16.2 Dashboard
Shows recent assignments and quick actions:
- create assignment
- continue setup
- continue review

### 16.3 Assignment overview page
Displays:
- assignment title
- course
- status
- counts of questions and submissions
- buttons for next steps

### 16.4 Questions page
Displays generated question parts in editable cards/table rows.

Actions:
- generate questions
- edit text
- edit marks
- add/delete/reorder

### 16.5 Reference Answers page
Displays each question part with its current model answer.

Actions:
- generate all
- regenerate one
- edit manually

### 16.6 Rubric page
Displays rubric criteria grouped by question part.

Actions:
- generate rubric
- edit criteria
- edit point values
- add/remove criteria

### 16.7 Submissions page
Displays upload UI and submissions table.

Columns:
- student name
- student ID
- grading status
- total score
- action

### 16.8 Review page
Displays all students and grading summaries, with ability to drill down.

### 16.9 Student review detail page
Displays:
- full student response
- each question part
- mapped answer text
- AI score vs max
- feedback
- editable final score
- editable final feedback
- finalize button

## 17. Error Handling / MVP Resilience
V1 should gracefully handle:
- failed LLM calls
- malformed model output
- partial grading failures
- empty student responses
- assignment parsing mistakes

Basic rules:
- never silently fail
- surface clear job status and errors
- allow retry for generation/grading jobs
- allow teacher manual edits even when AI output is bad

## 18. Security / Privacy Notes for V1
- Only authenticated teachers can access their own assignments.
- All assignment/submission records must be scoped to the logged-in teacher.
- API keys remain backend-only.
- Student data should not be exposed beyond the teacher account.
- V1 does not need advanced compliance features, but code should still follow sane privacy boundaries.

## 19. MVP Simplifications
To keep V1 realistic and buildable, the following simplifications are recommended:
- only one teacher role
- no student accounts
- no LMS integration
- text-first submission handling
- no OCR-heavy image parsing
- no multi-file per submission workflow
- no collaborative grading
- no advanced rubric analytics
- no live websocket updates unless easy; polling for jobs is acceptable
- no version history UI beyond current saved records

## 20. Future V2 Ideas (not in scope now)
- Canvas/LMS integration
- bulk PDF parsing and OCR improvements
- multiple graders / TA collaboration
- better confidence modeling and escalation rules
- rubric/version history
- plagiarism/similarity checks
- student-facing feedback portal
- analytics dashboard across assignments
- provider/model switching in settings
- S3 storage
- audit logs

## 21. Recommended Implementation Order
1. Auth + teacher model
2. Assignment CRUD
3. Question part entity + manual editing UI
4. LLM question decomposition
5. Reference answer generation
6. Rubric generation
7. Student submission upload
8. First-pass grading
9. Review/edit/finalize flow
10. Export CSV
11. Optional background jobs / Celery polish

## 22. Final Summary
Graider V1 should be a focused MVP that demonstrates a realistic AI-assisted grading workflow using a robust modern stack.

It should preserve the best ideas from the original prototype:
- structured grading flow
- teacher-controlled editing
- purple/sidebar UI identity
- question-by-question grading
- AI as an assistant, not a replacement

But it should replace the original implementation with a maintainable architecture:
- React frontend
- Django REST backend
- PostgreSQL database
- OpenAI integration with `gpt-5.4` and `gpt-5.4-mini`
- structured LLM outputs
- persistent grading entities

The result should be a strong MVP for demos, portfolio presentation, and future extension into a more fully featured grading platform.
