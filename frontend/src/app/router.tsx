import { createBrowserRouter, Navigate } from 'react-router-dom'

import { ProtectedLayout, PublicOnly } from './routeGuards'
import { AssignmentCreatePage } from '../pages/AssignmentCreatePage'
import { AssignmentOverviewPage } from '../pages/AssignmentOverviewPage'
import { AssignmentQuestionsPage } from '../pages/AssignmentQuestionsPage'
import { DashboardPage } from '../pages/DashboardPage'

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
      { path: 'assignments/new', element: <AssignmentCreatePage /> },
      { path: 'assignments/:assignmentId', element: <Navigate to="overview" replace /> },
      { path: 'assignments/:assignmentId/overview', element: <AssignmentOverviewPage /> },
      { path: 'assignments/:assignmentId/questions', element: <AssignmentQuestionsPage /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])
