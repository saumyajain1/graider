import { useEffect, useRef, useState, type PropsWithChildren } from 'react'
import { useBlocker } from 'react-router-dom'
import { getApiErrorMessage } from '../api/errors'
import { useWorkflowDrafts } from '../hooks/useDraftSaves'

import { LeaveContext, type LeaveAction } from '../hooks/useLeaveAction'

export function UnsavedChangesGuard({ children }: PropsWithChildren) {
  const drafts = useWorkflowDrafts()
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      drafts.isDirty() &&
      (currentLocation.pathname !== nextLocation.pathname ||
        currentLocation.search !== nextLocation.search),
  )
  const [action, setAction] = useState<LeaveAction | null>(null)
  const leaving = useRef(false)
  const [error, setError] = useState<string | null>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const open = blocker.state === 'blocked' || action !== null
  useEffect(() => {
    if (open && !dialog.current?.open) dialog.current?.showModal()
    else if (!open) dialog.current?.close()
  }, [open])
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!leaving.current && (drafts.isDirty() || drafts.isSaving)) {
        event.preventDefault()
        event.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [drafts])
  const stay = () => {
    if (drafts.isSaving) return
    if (blocker.state === 'blocked') blocker.reset()
    setAction(null)
    setError(null)
  }
  const leave = () => {
    if (blocker.state === 'blocked') blocker.proceed()
    else if (action) performAction(action)
    setAction(null)
    setError(null)
  }
  const performAction = (next: LeaveAction) => {
    leaving.current = true
    void Promise.resolve()
      .then(next)
      .finally(() => {
        leaving.current = false
      })
      .catch(() => {})
  }
  return (
    <LeaveContext.Provider
      value={(next) => {
        if (drafts.isDirty()) {
          setAction(() => next)
          setError(null)
        } else performAction(next)
      }}
    >
      {children}
      <dialog
        ref={dialog}
        aria-labelledby="unsaved-title"
        onCancel={(event) => {
          event.preventDefault()
          stay()
        }}
        className="m-auto w-full max-w-lg rounded-3xl p-6 shadow-xl backdrop:bg-slate-950/60"
      >
        <h2 id="unsaved-title" className="text-xl font-bold">
          You have unsaved changes
        </h2>
        <p className="mt-3 text-sm text-slate-600">
          Save your changes before leaving, discard them, or stay on this page.
        </p>
        {error && (
          <p role="alert" className="mt-3 text-sm text-rose-700">
            {error}
          </p>
        )}
        <div className="mt-5 flex flex-wrap gap-3">
          <button
            type="button"
            className="workflow-button"
            disabled={drafts.isSaving}
            onClick={async () => {
              setError(null)
              try {
                await drafts.saveAll({ dirtyOnly: true })
                drafts.discard()
                leave()
              } catch (error) {
                setError(
                  getApiErrorMessage(
                    error,
                    error instanceof Error ? error.message : 'Could not save changes.',
                  ),
                )
              }
            }}
          >
            {drafts.isSaving ? 'Saving…' : 'Save and leave'}
          </button>
          <button
            type="button"
            className="workflow-button"
            disabled={drafts.isSaving}
            onClick={() => {
              drafts.discard()
              leave()
            }}
          >
            Discard and leave
          </button>
          <button
            type="button"
            className="workflow-button"
            disabled={drafts.isSaving}
            onClick={stay}
          >
            Stay
          </button>
        </div>
      </dialog>
    </LeaveContext.Provider>
  )
}
