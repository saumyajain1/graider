export type Draft = { dirty: boolean; validate: () => void; save: () => Promise<unknown> }
export type SaveOptions = { dirtyOnly?: boolean }

export class DraftStore {
  private entries = new Map<string, Draft>()
  private saving = false
  register(key: string, draft: Draft) {
    this.entries.set(key, draft)
    return () => {
      if (this.entries.get(key) === draft) this.entries.delete(key)
    }
  }
  isDirty(key?: string) {
    return key
      ? Boolean(this.entries.get(key)?.dirty)
      : [...this.entries.values()].some((draft) => draft.dirty)
  }
  discard() {
    this.entries.forEach((draft) => {
      draft.dirty = false
    })
  }
  async saveAll({ dirtyOnly = false }: SaveOptions = {}) {
    if (this.saving) throw new Error('Please wait for saving to finish.')
    this.saving = true
    try {
      const snapshot = [...this.entries.entries()]
      snapshot.forEach(([, draft]) => {
        if (!dirtyOnly || draft.dirty) draft.validate()
      })
      for (const [key, draft] of snapshot)
        if (draft.dirty) {
          await draft.save()
          const current = this.entries.get(key)
          if (current) current.dirty = false
        }
    } finally {
      this.saving = false
    }
  }
}
