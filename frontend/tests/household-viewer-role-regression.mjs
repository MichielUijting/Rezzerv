import assert from 'node:assert/strict'
import { normalizeHouseholdAccessContext } from '../src/lib/authSession.js'

const adminContext = normalizeHouseholdAccessContext({
  id: '1',
  active_household_id: '1',
  display_role: 'admin',
  role: 'owner',
  is_viewer: true,
  permissions: {
    'article.create': true,
    'article_group.create': true,
    'article.update': true,
  },
})

assert.equal(adminContext.is_viewer, false, 'admin/owner mag nooit als kijker worden behandeld')
assert.equal(adminContext.can_process_receipts, true, 'admin/owner moet kassabonnen kunnen verwerken')

const memberContext = normalizeHouseholdAccessContext({
  display_role: 'lid',
  role: 'household.member',
  is_viewer: true,
  permissions: {},
})

assert.equal(memberContext.is_viewer, false, 'lid mag niet door een conflicterend legacyveld als kijker gelden')
assert.equal(memberContext.can_process_receipts, true, 'lid moet kassabonnen kunnen verwerken')

const viewerContext = normalizeHouseholdAccessContext({
  display_role: 'viewer',
  role: 'household.viewer',
  is_viewer: false,
  permissions: {},
})

assert.equal(viewerContext.is_viewer, true, 'een echte kijker moet kijker blijven')
assert.equal(viewerContext.can_process_receipts, false, 'een echte kijker mag kassabonnen niet verwerken')

const permissionContext = normalizeHouseholdAccessContext({
  display_role: 'viewer',
  role: 'household.viewer',
  is_viewer: true,
  permissions: {
    'receipts.process': true,
  },
})

assert.equal(permissionContext.can_process_receipts, true, 'een expliciete receipts.process-permissie moet worden herkend')

console.log('HOUSEHOLD_VIEWER_ROLE_REGRESSION=PASS')
