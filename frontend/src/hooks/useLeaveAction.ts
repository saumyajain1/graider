import { createContext, useContext } from 'react'

export type LeaveAction = () => void | Promise<unknown>
export const LeaveContext = createContext<(action: LeaveAction) => void>((action) => {
  void Promise.resolve()
    .then(action)
    .catch(() => {})
})
export const useLeaveAction = () => useContext(LeaveContext)
