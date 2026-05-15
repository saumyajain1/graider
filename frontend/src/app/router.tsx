import { createBrowserRouter, Navigate } from 'react-router-dom'

import { ProtectedLayout, PublicOnly } from './routeGuards'
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
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])
