import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getApiErrorMessage } from '../api/errors'
import { useWorkflowDrafts } from '../hooks/useDraftSaves'
import { Icon } from './Icon'

export function WorkflowContinue({
  to,
  children,
  disabled = false,
  validate,
}: {
  to: string
  children: string
  disabled?: boolean
  validate?: () => Promise<void>
}) {
  const navigate = useNavigate()
  const drafts = useWorkflowDrafts()
  const [isContinuing, setIsContinuing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return (
    <div>
      <button
        type="button"
        className="workflow-button"
        disabled={disabled || isContinuing || drafts.isSaving}
        aria-busy={isContinuing}
        onClick={async () => {
          setError(null)
          setIsContinuing(true)
          try {
            await drafts.saveAll()
            await validate?.()
            navigate(to)
          } catch (error) {
            setError(
              getApiErrorMessage(
                error,
                error instanceof Error
                  ? error.message
                  : 'Could not save your changes. Please try again.',
              ),
            )
          } finally {
            setIsContinuing(false)
          }
        }}
      >
        <span>{isContinuing ? 'Saving…' : `Save and continue to ${children}`}</span>
        <Icon name={isContinuing ? 'spinner' : 'forward'} />
      </button>
      {error ? (
        <p role="alert" className="mt-3 max-w-xl text-sm text-rose-700">
          {error}
        </p>
      ) : null}
    </div>
  )
}

export function WorkflowBack({ to, children }: { to: string; children: string }) {
  return (
    <Link to={to} className="workflow-button">
      <Icon name="back" />
      {children}
    </Link>
  )
}
