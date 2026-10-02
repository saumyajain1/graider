export function marksInCents(value: string | null | undefined): number | null {
  if (!value || !/^\d+(?:\.\d{1,2})?$/.test(value.trim())) return null
  const amount = Number(value)
  return Number.isFinite(amount) && amount > 0 && amount <= 9999.99
    ? Math.round(amount * 100)
    : null
}

export function requireMarks(value: string | null | undefined, label: string) {
  if (marksInCents(value) === null)
    throw new Error(
      `${label}: enter total marks greater than zero, with at most two decimal places.`,
    )
}
