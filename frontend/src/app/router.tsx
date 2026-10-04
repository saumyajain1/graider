import { createBrowserRouter, Navigate } from 'react-router-dom'

import { ProtectedLayout, PublicOnly } from './routeGuards'
import { PageError } from '../components/PageError'
import { AssignmentCreatePage } from '../pages/AssignmentCreatePage'
import { AssignmentOverviewPage } from '../pages/AssignmentOverviewPage'
import { AssignmentQuestionsPage } from '../pages/AssignmentQuestionsPage'
import { AssignmentReferenceAnswersPage } from '../pages/AssignmentReferenceAnswersPage'
import { AssignmentReviewPage } from '../pages/AssignmentReviewPage'
import { AssignmentRubricPage } from '../pages/AssignmentRubricPage'
import { AssignmentSubmissionsPage } from '../pages/AssignmentSubmissionsPage'
import { DashboardPage } from '../pages/DashboardPage'
import { PasswordRecoveryPage } from '../pages/PasswordRecoveryPage'
import { ProfilePage } from '../pages/ProfilePage'
import { SubmissionReviewPage } from '../pages/SubmissionReviewPage'

export const router = createBrowserRouter([
  {
    path: '/forgot-password',
    element: <PasswordRecoveryPage />,
    errorElement: <PageError standalone />,
  },
  {
    path: '/reset-password',
    element: <PasswordRecoveryPage confirm />,
    errorElement: <PageError standalone />,
  },
  {
    path: '/login',
    element: <PublicOnly />,
    errorElement: <PageError standalone />,
  },
  {
    path: '/',
    element: <ProtectedLayout />,
    errorElement: <PageError standalone />,
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
    ].map((route) => ({ ...route, errorElement: <PageError /> })),
  },
])
