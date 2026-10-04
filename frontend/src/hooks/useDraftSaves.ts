import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

import { DraftStore, type Draft, type SaveOptions } from '../lib/draftStore'

export function useDraftSaves() {
  const shared = useContext(DraftContext)
  const store = useRef(new DraftStore())
  const saving = useRef(false)
  const [isSaving, setIsSaving] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  const publish = useCallback(() => {
    setHasChanges(store.current.isDirty())
  }, [])
  const register = useCallback(
    (key: string, draft: Draft) => {
      const unregister = store.current.register(key, draft)
      publish()
      return () => {
        unregister()
        // Cleanup and replacement happen in the same effect cycle.
        queueMicrotask(publish)
      }
    },
    [publish],
  )
  const isDirty = useCallback((key?: string) => store.current.isDirty(key), [])
  const discard = () => {
    store.current.discard()
    publish()
  }
  const saveAll = async (options?: SaveOptions) => {
    if (saving.current) throw new Error('Please wait for saving to finish.')
    saving.current = true
    setIsSaving(true)
    try {
      await store.current.saveAll(options)
    } finally {
      saving.current = false
      publish()
      setIsSaving(false)
    }
  }
  return shared ?? { register, saveAll, isSaving, hasChanges, isDirty, discard }
}

export type DraftSaves = {
  register: (key: string, draft: Draft) => () => void
  saveAll: (options?: SaveOptions) => Promise<void>
  isSaving: boolean
  hasChanges: boolean
  isDirty: (key?: string) => boolean
  discard: () => void
}
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
