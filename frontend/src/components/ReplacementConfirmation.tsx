import { useEffect, useId, useRef } from 'react'
import type { useConfirmation } from '../hooks/useConfirmation'

export function ReplacementConfirmation({
  confirmation,
  titleText = 'Replace content with AI?',
  confirmLabel = 'Replace with AI',
  cancelLabel = 'Keep my content',
}: {
  confirmation: ReturnType<typeof useConfirmation>
  titleText?: string
  confirmLabel?: string
  cancelLabel?: string
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const title = useId()
  useEffect(() => {
    if (confirmation.message && !dialog.current?.open) dialog.current?.showModal()
    else if (!confirmation.message) dialog.current?.close()
  }, [confirmation.message])
  return (
    <dialog
      ref={dialog}
      aria-labelledby={title}
      onCancel={(event) => {
        event.preventDefault()
        confirmation.answer(false)
      }}
      className="m-auto w-full max-w-lg rounded-3xl p-6 shadow-xl backdrop:bg-slate-950/60"
    >
      <h2 id={title} className="text-xl font-bold">
        {titleText}
      </h2>
      <p className="mt-3 text-sm text-slate-600">{confirmation.message}</p>
      <div className="mt-5 flex gap-3">
        <button
          type="button"
          className="workflow-button"
          onClick={() => confirmation.answer(false)}
        >
          {cancelLabel}
        </button>
        <button type="button" className="workflow-button" onClick={() => confirmation.answer(true)}>
          {confirmLabel}
        </button>
      </div>
    </dialog>
  )
}
