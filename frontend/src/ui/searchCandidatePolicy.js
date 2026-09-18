export const MAX_VISIBLE_SEARCH_CANDIDATES = 5

export function limitSearchCandidates(items = []) {
  if (!Array.isArray(items)) return []
  return items.slice(0, MAX_VISIBLE_SEARCH_CANDIDATES)
}
