import type { ButtonHTMLAttributes } from 'react'
import { Icon } from './Icon'

export function AIButton({
  busy = false,
  children,
  className = '',
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { busy?: boolean }) {
  return (
    <button
      {...props}
      type="button"
      disabled={disabled || busy}
      aria-busy={busy}
      title="Uses AI"
      className={`ai-button ${className}`}
    >
      <Icon name={busy ? 'spinner' : 'sparkles'} />
      <span>{children}</span>
      <span className="sr-only"> (uses AI)</span>
    </button>
  )
}
