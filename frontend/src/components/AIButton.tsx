import type { ButtonHTMLAttributes } from 'react'
import { Icon } from './Icon'
import type { AIJob } from '../api/jobs'
import { jobLabels, runnableJobStates } from '../lib/aiJobs'

export function AIButton({
  busy = false,
  job,
  children,
  className = '',
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { busy?: boolean; job?: AIJob }) {
  const working = job ? runnableJobStates.includes(job.state) : busy
  return (
    <button
      {...props}
      type="button"
      disabled={disabled || working || Boolean(job)}
      aria-busy={working}
      title="Uses AI"
      className={`ai-button ${className}`}
    >
      <Icon name={working ? 'spinner' : 'sparkles'} />
      <span>{job ? (job.cancel_requested ? 'Cancelling…' : jobLabels[job.state]) : children}</span>
      <span className="sr-only"> (uses AI)</span>
    </button>
  )
}
