import assert from 'node:assert/strict'
import {
  snapshotJumboImportContext, jumboImportContextMatches,
  jumboImportContextHeaders, verifyJumboImportContext,
} from '../src/features/storeConnections/jumboImportContext.js'

const original = { user_id: 'test-user-1', active_household_id: 'household-a', context_type: 'regular' }
const guard = snapshotJumboImportContext(original)
assert.deepEqual(guard, { userId: 'test-user-1', householdId: 'household-a' })
assert.equal(Object.isFrozen(guard), true)
assert.deepEqual(jumboImportContextHeaders(guard), {
  'X-Inhuis-Expected-User': 'test-user-1',
  'X-Inhuis-Expected-Household': 'household-a',
})
assert.equal(jumboImportContextMatches(guard, { ...original }), true)
for (const session of [
  null, {}, { ...original, user_id: 'other-user' },
  { ...original, active_household_id: 'household-b' },
  { ...original, context_type: 'none' },
  { ...original, active_household_id: '0' },
]) {
  assert.equal(jumboImportContextMatches(guard, session), false)
  await assert.rejects(() => verifyJumboImportContext(guard, async () => session),
    /gewijzigd/)
}
await assert.rejects(() => verifyJumboImportContext(guard, async () => {
  throw new Error('Session expired')
}), /Session expired/)
assert.deepEqual(await verifyJumboImportContext(guard, async () => original), jumboImportContextHeaders(guard))
console.log('Jumbo context binding contract: OK')
