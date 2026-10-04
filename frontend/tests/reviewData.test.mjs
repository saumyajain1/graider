import assert from 'node:assert/strict'
import test from 'node:test'
import { isSubmissionGrading } from '../src/api/reviewData.ts'

function ungraded() {
  return {
    submission: {
      id: 1,
      assignment: 2,
      student_name: 'Student',
      grading_status: 'pending',
      total_score: null,
    },
    answer_parts: [],
    grading_results: [],
    questions: [
      {
        question_part_id: 3,
        question_text: 'Question',
        display_label: '1',
        max_marks: '5.00',
        criteria: [{ id: 4, title: 'Accuracy', description: 'Correct answer', max_points: '5.00' }],
      },
    ],
    reference_answers: [{ question_part_id: 3, answer_text: 'Reference' }],
  }
}

function graded() {
  const data = ungraded()
  data.grading_results = [
    {
      question_part_id: 3,
      max_score: '5.00',
      final_feedback: 'Feedback',
      ai_score: '0.00',
      final_score: '0.00',
      criterion_results: [
        {
          criterion_id: 4,
          title: 'Accuracy',
          description: 'Correct answer',
          max_points: '5.00',
          ai_score: '0.00',
          final_score: '0.00',
          ai_feedback: 'No correct answer',
          final_feedback: 'No correct answer',
        },
      ],
    },
  ]
  return data
}

test('accepts ungraded review data and explicit zero criterion grades', () => {
  assert.equal(isSubmissionGrading(ungraded()), true)
  assert.equal(isSubmissionGrading(graded()), true)
})

test('rejects the old backend response before the page reads missing questions', () => {
  const data = ungraded()
  delete data.questions
  delete data.reference_answers
  assert.equal(isSubmissionGrading(data), false)
})

test('rejects malformed nested rubric and result arrays', () => {
  const data = ungraded()
  data.questions[0].criteria = null
  assert.equal(isSubmissionGrading(data), false)
  const result = graded()
  delete result.grading_results[0].criterion_results
  assert.equal(isSubmissionGrading(result), false)
})

test('rejects invalid score types that would crash editor formatting', () => {
  const data = graded()
  data.grading_results[0].criterion_results[0].final_score = 2
  assert.equal(isSubmissionGrading(data), false)
})

test('rejects non-JSON and non-object responses', () => {
  for (const value of [null, [], '<html>Error</html>', { submission: null }]) {
    assert.equal(isSubmissionGrading(value), false)
  }
})
