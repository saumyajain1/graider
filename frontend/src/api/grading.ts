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

export function generateRubric(
  assignmentId: string,
  payload?: { question_part_id?: number },
) {
  return apiRequest<RubricQuestion[]>(`/api/assignments/${assignmentId}/rubric/generate`, {
    method: 'POST',
    body: JSON.stringify(payload ?? {}),
  })
}
