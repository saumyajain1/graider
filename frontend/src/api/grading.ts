import { apiRequest } from './client'

export type ReferenceAnswerItem = {
  id: number | null
  question_part_id: number
  part_key: string
  source_label: string
  display_label: string
  question_text: string
  max_marks: string | null
  answer_text: string
  version: number | null
  source: 'ai' | 'teacher' | null
}

export type RubricCriterion = {
  id: number
  title: string
  description: string
  max_points: string
  display_order: number
  created_by_ai: boolean
  created_at: string
  updated_at: string
}

export type RubricQuestion = {
  question_part_id: number
  part_key: string
  source_label: string
  display_label: string
  question_text: string
  max_marks: string | null
  criteria: RubricCriterion[]
}

export type StudentSubmission = {
  id: number
  assignment: number
  student_name: string
  student_identifier: string
  raw_response_text: string
  response_file_url: string | null
  response_filename: string | null
  ingestion_notes: string
  upload_source: 'manual' | 'file' | 'csv'
  grading_status: 'pending' | 'grading' | 'graded' | 'reviewed' | 'finalized' | 'failed'
  total_score: string | null
  last_error: string
  finalized_at: string | null
  created_at: string
  updated_at: string
}

export type SubmissionImport = {
  id: number
  original_filename: string
  source_file_url: string
  row_count: number
  created_at: string
}

export type SubmissionAnswerPart = {
  id: number
  question_part_id: number
  part_key: string
  source_label: string
  display_label: string
  question_text: string
  extracted_answer_text: string
  mapping_confidence: string | null
  created_at: string
  updated_at: string
}

export type GradingResult = {
  id: number
  question_part_id: number
  part_key: string
  source_label: string
  display_label: string
  question_text: string
  ai_score: string | null
  final_score: string | null
  max_score: string
  ai_feedback: string
  final_feedback: string
  reasoning_summary: string
  confidence_score: string | null
  needs_review: boolean
  created_at: string
  updated_at: string
}

export type SubmissionGrading = {
  submission: StudentSubmission
  answer_parts: SubmissionAnswerPart[]
  grading_results: GradingResult[]
}

export type GradeAllResponse = {
  graded_count: number
  failed_count: number
  submissions: StudentSubmission[]
}

export function listReferenceAnswers(assignmentId: string) {
  return apiRequest<ReferenceAnswerItem[]>(`/api/assignments/${assignmentId}/reference-answers`)
}

export function createReferenceAnswer(
  assignmentId: string,
  payload: { question_part_id: number; answer_text: string },
) {
  return apiRequest<ReferenceAnswerItem>(`/api/assignments/${assignmentId}/reference-answers`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateReferenceAnswer(
  referenceAnswerId: number,
  payload: { answer_text: string; source?: 'ai' | 'teacher' },
) {
  return apiRequest<ReferenceAnswerItem>(`/api/reference-answers/${referenceAnswerId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function generateReferenceAnswers(
  assignmentId: string,
  payload?: { question_part_id?: number },
) {
  return apiRequest<ReferenceAnswerItem[]>(
    `/api/assignments/${assignmentId}/reference-answers/generate`,
    {
      method: 'POST',
      body: JSON.stringify(payload ?? {}),
    },
  )
}

export function listRubric(assignmentId: string) {
  return apiRequest<RubricQuestion[]>(`/api/assignments/${assignmentId}/rubric`)
}

export function createRubricCriterion(
  assignmentId: string,
  payload: {
    question_part_id: number
    title: string
    description: string
    max_points: string
  },
) {
  return apiRequest<RubricCriterion>(`/api/assignments/${assignmentId}/rubric`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateRubricCriterion(
  criterionId: number,
  payload: Partial<Pick<RubricCriterion, 'title' | 'description' | 'max_points'>>,
) {
  return apiRequest<RubricCriterion>(`/api/rubric-criteria/${criterionId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function deleteRubricCriterion(criterionId: number) {
  return apiRequest<void>(`/api/rubric-criteria/${criterionId}`, {
    method: 'DELETE',
  })
}

export function generateRubric(assignmentId: string, payload?: { question_part_id?: number }) {
  return apiRequest<RubricQuestion[]>(`/api/assignments/${assignmentId}/rubric/generate`, {
    method: 'POST',
    body: JSON.stringify(payload ?? {}),
  })
}

export function listSubmissions(assignmentId: string) {
  return apiRequest<StudentSubmission[]>(`/api/assignments/${assignmentId}/submissions`)
}

export function listSubmissionImports(assignmentId: string) {
  return apiRequest<SubmissionImport[]>(`/api/assignments/${assignmentId}/imports`)
}

export function createSubmission(
  assignmentId: string,
  payload: {
    student_name: string
    student_identifier?: string
    raw_response_text?: string
    response_file?: File | null
  },
) {
  const formData = new FormData()
  formData.append('student_name', payload.student_name)
  formData.append('student_identifier', payload.student_identifier ?? '')
  formData.append('raw_response_text', payload.raw_response_text ?? '')
  if (payload.response_file) {
    formData.append('response_file', payload.response_file)
  }

  return apiRequest<StudentSubmission>(`/api/assignments/${assignmentId}/submissions`, {
    method: 'POST',
    body: formData,
  })
}

export function importSubmissionsCsv(assignmentId: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)

  return apiRequest<StudentSubmission[]>(
    `/api/assignments/${assignmentId}/submissions/import-csv`,
    {
      method: 'POST',
      body: formData,
    },
  )
}

export function getSubmission(submissionId: number) {
  return apiRequest<StudentSubmission>(`/api/submissions/${submissionId}`)
}

export function gradeSubmission(submissionId: number) {
  return apiRequest<StudentSubmission>(`/api/submissions/${submissionId}/grade`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function gradeAllSubmissions(assignmentId: string) {
  return apiRequest<GradeAllResponse>(`/api/assignments/${assignmentId}/grade-all`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function getSubmissionGrading(submissionId: number) {
  return apiRequest<SubmissionGrading>(`/api/submissions/${submissionId}/grading`)
}

export function updateGradingResult(
  gradingResultId: number,
  payload: {
    final_score?: string | null
    final_feedback?: string
    needs_review?: boolean
  },
) {
  return apiRequest<GradingResult>(`/api/grading-results/${gradingResultId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function finalizeSubmission(submissionId: number) {
  return apiRequest<StudentSubmission>(`/api/submissions/${submissionId}/finalize`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}
