import { apiRequest } from './client'

export type Assignment = {
  id: number
  title: string
  course_name: string
  description: string
  raw_assignment_text: string
  source_file_url: string | null
  source_filename: string | null
  ingestion_notes: string
  status: string
  question_count: number
  submission_count: number
  created_at: string
  updated_at: string
}

export type QuestionPart = {
  id: number
  assignment: number
  part_key: string
  source_label: string
  display_label: string
  parent_key: string
  part_type: 'context' | 'question'
  text: string
  max_marks: string | null
  display_order: number
  created_by_ai: boolean
  created_at: string
  updated_at: string
}

export type AssignmentPayload = {
  title: string
  course_name: string
  description: string
  raw_assignment_text: string
  source_file?: File | null
  source_text_mode?: 'file' | 'text'
}

function toAssignmentFormData(payload: AssignmentPayload) {
  const formData = new FormData()
  formData.append('title', payload.title)
  formData.append('course_name', payload.course_name)
  formData.append('description', payload.description)
  formData.append('raw_assignment_text', payload.raw_assignment_text)
  if (payload.source_text_mode) formData.append('source_text_mode', payload.source_text_mode)

  if (payload.source_file) {
    formData.append('source_file', payload.source_file)
  }

  return formData
}

export function listAssignments() {
  return apiRequest<Assignment[]>('/api/assignments/')
}

export function getAssignment(assignmentId: string) {
  return apiRequest<Assignment>(`/api/assignments/${assignmentId}`)
}

export function createAssignment(payload: AssignmentPayload) {
  return apiRequest<Assignment>('/api/assignments/', {
    method: 'POST',
    body: toAssignmentFormData(payload),
  })
}

export function updateAssignment(assignmentId: string, payload: AssignmentPayload) {
  return apiRequest<Assignment>(`/api/assignments/${assignmentId}`, {
    method: 'PATCH',
    body: toAssignmentFormData(payload),
  })
}

export function deleteAssignment(assignmentId: string) {
  return apiRequest<void>(`/api/assignments/${assignmentId}`, {
    method: 'DELETE',
  })
}

export function listQuestions(assignmentId: string) {
  return apiRequest<QuestionPart[]>(`/api/assignments/${assignmentId}/questions`)
}

export function createQuestion(
  assignmentId: string,
  payload: {
    source_label?: string
    parent_key?: string
    text: string
    max_marks: string | null
    part_type: 'context' | 'question'
  },
) {
  return apiRequest<QuestionPart>(`/api/assignments/${assignmentId}/questions`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateQuestion(
  questionId: number,
  payload: {
    source_label?: string
    parent_key?: string
    text: string
    max_marks: string | null
    part_type: 'context' | 'question'
  },
) {
  return apiRequest<QuestionPart>(`/api/assignments/questions/${questionId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function deleteQuestion(questionId: number) {
  return apiRequest<void>(`/api/assignments/questions/${questionId}`, {
    method: 'DELETE',
  })
}

export function reorderQuestions(assignmentId: string, questionIds: number[]) {
  return apiRequest<QuestionPart[]>(`/api/assignments/${assignmentId}/questions/reorder`, {
    method: 'POST',
    body: JSON.stringify({ question_ids: questionIds }),
  })
}

export function generateQuestions(assignmentId: string, replaceExisting = true) {
  return apiRequest<QuestionPart[]>(`/api/assignments/${assignmentId}/questions/generate`, {
    method: 'POST',
    body: JSON.stringify({ replace_existing: replaceExisting }),
  })
}

export function previewAssignmentSource(assignmentId: string, file: File) {
  const body = new FormData()
  body.append('source_file', file)
  return apiRequest<{ extracted_text: string; ingestion_notes: string }>(
    `/api/assignments/${assignmentId}/source-preview`,
    { method: 'POST', body },
  )
}
