// A Jumbo browser result is never an authority for an Inhuis user or household.
// Capture /api/session before reserving an import run and require exactly the
// same backend-resolved identity on each subsequent write.
export function snapshotJumboImportContext(session) {
  const userId = String(session?.user_id || session?.user?.id || '').trim()
  const householdId = String(session?.active_household_id ?? '').trim()
  if (!userId || !householdId || householdId === '0' ||
      (session?.context_type && session.context_type !== 'regular')) {
    throw new Error('Geen geldig actief Inhuis-huishouden voor Jumbo. Log opnieuw in.')
  }
  return Object.freeze({ userId, householdId })
}

export function jumboImportContextMatches(expected, current) {
  if (!expected?.userId || !expected?.householdId) return false
  try {
    const actual = snapshotJumboImportContext(current)
    return actual.userId === expected.userId && actual.householdId === expected.householdId
  } catch {
    return false
  }
}

export function jumboImportContextHeaders(expected) {
  if (!expected?.userId || !expected?.householdId ||
      expected.userId.length > 128 || expected.householdId.length > 128) {
    throw new Error('Jumbo-import is niet meer aan een Inhuis-sessie gekoppeld.')
  }
  return {
    'X-Inhuis-Expected-User': expected.userId,
    'X-Inhuis-Expected-Household': expected.householdId,
  }
}

export async function verifyJumboImportContext(expected, fetchSession) {
  if (!jumboImportContextMatches(expected, await fetchSession())) {
    throw new Error('De Inhuis-gebruiker of het huishouden is gewijzigd. De Jumbo-import is veilig gestopt.')
  }
  return jumboImportContextHeaders(expected)
}
