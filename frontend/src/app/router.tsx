import { createBrowserRouter, Navigate } from 'react-router-dom'

import { ProtectedLayout, PublicOnly } from './routeGuards'
import { AssignmentCreatePage } from '../pages/AssignmentCreatePage'
import { AssignmentOverviewPage } from '../pages/AssignmentOverviewPage'
import { AssignmentQuestionsPage } from '../pages/AssignmentQuestionsPage'
import { AssignmentReferenceAnswersPage } from '../pages/AssignmentReferenceAnswersPage'
import { AssignmentReviewPage } from '../pages/AssignmentReviewPage'
import { AssignmentRubricPage } from '../pages/AssignmentRubricPage'
import { AssignmentSubmissionsPage } from '../pages/AssignmentSubmissionsPage'
import { DashboardPage } from '../pages/DashboardPage'
import { ProfilePage } from '../pages/ProfilePage'
import { SubmissionReviewPage } from '../pages/SubmissionReviewPage'

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <PublicOnly />,
  },
  {
    path: '/',
    element: <ProtectedLayout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'profile', element: <ProfilePage /> },
      { path: 'assignments/new', element: <AssignmentCreatePage /> },
      { path: 'assignments/:assignmentId', element: <Navigate to="overview" replace /> },
      { path: 'assignments/:assignmentId/overview', element: <AssignmentOverviewPage /> },
      { path: 'assignments/:assignmentId/questions', element: <AssignmentQuestionsPage /> },
      {
        path: 'assignments/:assignmentId/reference-answers',
        element: <AssignmentReferenceAnswersPage />,
      },
      { path: 'assignments/:assignmentId/rubric', element: <AssignmentRubricPage /> },
      { path: 'assignments/:assignmentId/submissions', element: <AssignmentSubmissionsPage /> },
      { path: 'assignments/:assignmentId/review', element: <AssignmentReviewPage /> },
      {
        path: 'assignments/:assignmentId/review/:submissionId',
        element: <SubmissionReviewPage />,
      },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])
