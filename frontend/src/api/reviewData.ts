import type { SubmissionGrading } from './grading'

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function score(value: unknown) {
  return value === null || typeof value === 'string'
}

function criterion(value: unknown) {
  return (
    record(value) &&
    typeof value.title === 'string' &&
    typeof value.description === 'string' &&
    typeof value.max_points === 'string'
  )
}

// TypeScript cannot validate JSON at runtime. Check the fields the review renders
// before accepting a response, including responses from an older server process.
export function isSubmissionGrading(value: unknown): value is SubmissionGrading {
  if (!record(value) || !record(value.submission)) return false
  const submission = value.submission
  return (
    typeof submission.id === 'number' &&
    typeof submission.assignment === 'number' &&
    typeof submission.student_name === 'string' &&
    typeof submission.grading_status === 'string' &&
    score(submission.total_score) &&
    Array.isArray(value.answer_parts) &&
    value.answer_parts.every(
      (answer) =>
        record(answer) &&
        typeof answer.question_part_id === 'number' &&
        typeof answer.extracted_answer_text === 'string',
    ) &&
    Array.isArray(value.questions) &&
    value.questions.every(
      (question) =>
        record(question) &&
        typeof question.question_part_id === 'number' &&
        typeof question.question_text === 'string' &&
        typeof question.display_label === 'string' &&
        score(question.max_marks) &&
        Array.isArray(question.criteria) &&
        question.criteria.every(
          (row) => criterion(row) && record(row) && typeof row.id === 'number',
        ),
    ) &&
    Array.isArray(value.reference_answers) &&
    value.reference_answers.every(
      (answer) =>
        record(answer) &&
        typeof answer.question_part_id === 'number' &&
        typeof answer.answer_text === 'string',
    ) &&
    Array.isArray(value.grading_results) &&
    value.grading_results.every(
      (result) =>
        record(result) &&
        typeof result.question_part_id === 'number' &&
        typeof result.max_score === 'string' &&
        typeof result.final_feedback === 'string' &&
        score(result.ai_score) &&
        score(result.final_score) &&
        Array.isArray(result.criterion_results) &&
        result.criterion_results.every(
          (row) =>
            criterion(row) &&
            record(row) &&
            typeof row.criterion_id === 'number' &&
            score(row.ai_score) &&
            score(row.final_score) &&
            typeof row.ai_feedback === 'string' &&
            typeof row.final_feedback === 'string',
        ),
    )
  )
}
