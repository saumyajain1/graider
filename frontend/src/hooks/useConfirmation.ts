import { useEffect, useRef, useState } from 'react'

export function useConfirmation() {
  const [message, setMessage] = useState<string | null>(null)
  const pending = useRef<((confirmed: boolean) => void) | null>(null)
  useEffect(
    () => () => {
      pending.current?.(false)
    },
    [],
  )
  const answer = (confirmed: boolean) => {
    pending.current?.(confirmed)
    pending.current = null
    setMessage(null)
  }
  const ask = (text: string) =>
    new Promise<boolean>((resolve) => {
      pending.current?.(false)
      pending.current = resolve
      setMessage(text)
    })
  return { message, ask, answer }
}
