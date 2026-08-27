export const MIN_RESIZABLE_COLUMN_WIDTH = 56

function normalizedWidth(value) {
  return Math.max(1, Math.round(Number(value) || 1))
}

export function tableWidthTotal(widths) {
  return (widths || []).reduce((sum, value) => sum + normalizedWidth(value), 0)
}

export function resizeTableBoundary(widths, boundaryIndex, delta, minimumWidth = MIN_RESIZABLE_COLUMN_WIDTH) {
  const startWidths = Array.isArray(widths) ? widths.map(normalizedWidth) : []
  const leftIndex = Number(boundaryIndex)
  const rightIndex = leftIndex + 1

  if (!Number.isInteger(leftIndex) || leftIndex < 0 || rightIndex >= startWidths.length) {
    return startWidths
  }

  const leftStart = startWidths[leftIndex]
  const rightStart = startWidths[rightIndex]
  const normalizedMinimum = Math.max(1, Math.round(Number(minimumWidth) || MIN_RESIZABLE_COLUMN_WIDTH))
  const leftMinimum = Math.min(normalizedMinimum, leftStart)
  const rightMinimum = Math.min(normalizedMinimum, rightStart)
  const requestedDelta = Math.round(Number(delta) || 0)
  const minimumDelta = leftMinimum - leftStart
  const maximumDelta = rightStart - rightMinimum
  const appliedDelta = Math.max(minimumDelta, Math.min(maximumDelta, requestedDelta))

  const nextWidths = [...startWidths]
  nextWidths[leftIndex] = leftStart + appliedDelta
  nextWidths[rightIndex] = rightStart - appliedDelta
  return nextWidths
}
