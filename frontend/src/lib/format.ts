export function formatStatus(status: string) {
  const label = status.replace(/_/g, ' ')
  return label.charAt(0).toUpperCase() + label.slice(1)
}
