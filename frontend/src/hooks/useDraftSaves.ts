import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

type Draft = { dirty: boolean; validate: () => void; save: () => Promise<unknown> }

export function useDraftSaves() {
  const entries = useRef(new Map<string, Draft>())
  const saving = useRef(false)
  const [isSaving, setIsSaving] = useState(false)
  const register = useCallback((key: string, draft: Draft) => {
    entries.current.set(key, draft)
    return () => {
      if (entries.current.get(key) === draft) entries.current.delete(key)
    }
  }, [])
  const saveAll = async () => {
    if (saving.current) throw new Error('Please wait for saving to finish.')
    saving.current = true
    setIsSaving(true)
    try {
      // Snapshot all drafts before query refreshes can change the registered entries.
      const drafts = [...entries.current.values()]
      drafts.forEach((draft) => draft.validate())
      for (const draft of drafts) if (draft.dirty) await draft.save()
    } finally {
      saving.current = false
      setIsSaving(false)
    }
  }
  return { register, saveAll, isSaving }
}

export type DraftSaves = ReturnType<typeof useDraftSaves>
const DraftContext = createContext<DraftSaves | null>(null)
export const WorkflowDraftProvider = DraftContext.Provider

export function useDraft(key: string, draft: Draft, supplied?: DraftSaves) {
  const context = useContext(DraftContext)
  const register = (supplied ?? context)?.register
  useEffect(() => register?.(key, draft), [register, key, draft])
}

export function useWorkflowDrafts() {
  const drafts = useContext(DraftContext)
  if (!drafts) throw new Error('Workflow drafts are unavailable.')
  return drafts
}
