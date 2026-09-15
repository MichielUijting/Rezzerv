export function mergeIncomingFormStatePreservingDirtyFields(currentState = {}, incomingState = {}, dirtyFields = []) {
  const dirty = dirtyFields instanceof Set ? dirtyFields : new Set(dirtyFields || [])
  const next = { ...currentState }

  Object.entries(incomingState || {}).forEach(([key, value]) => {
    if (!dirty.has(key)) next[key] = value
  })

  return next
}
