import assert from 'node:assert/strict'

function createStorage() {
  const values = new Map()
  return {
    getItem: (key) => values.get(key) ?? null,
    removeItem: (key) => values.delete(key),
    setItem: (key, value) => values.set(key, String(value)),
  }
}

globalThis.window = {
  localStorage: createStorage(),
  sessionStorage: createStorage(),
}

const {
  clearAuthSession,
  readStoredAuthContext,
  storeAuthContext,
} = await import('../src/lib/authSession.js')

const none = storeAuthContext({
  user_id: 'platform-user',
  email: 'platform@example.test',
  context_type: 'none',
  active_household_id: null,
  active_household_name: '',
  role: null,
  display_role: null,
  permissions: {},
  supported_permissions: [],
  is_platform_superuser: false,
  is_frontteam: false,
})

assert.equal(none.context_type, 'none')
assert.equal(none.active_household_id, null)
assert.equal(none.role, null)
assert.equal(none.display_role, null)
assert.notEqual(none.active_household_id, '0')
assert.notEqual(none.active_household_id, '1')
assert.notEqual(none.active_household_id, 'demo-household')
assert.deepEqual(none.permissions, {})
assert.equal(none.is_platform_superuser, false)
assert.equal(readStoredAuthContext(), none)

const regular = storeAuthContext({
  user_id: 'regular-user',
  context_type: 'regular',
  active_household_id: 'household-1',
  role: 'admin',
  display_role: 'admin',
  permissions: { 'admin.access': true },
})

assert.equal(regular.context_type, 'regular')
assert.equal(regular.active_household_id, 'household-1')
assert.equal(regular.role, 'admin')
assert.equal(regular.display_role, 'admin')
assert.equal(regular.permissions['admin.access'], true)

const system = storeAuthContext({
  user_id: 'system-user',
  context_type: 'system',
  active_household_id: '0',
  role: 'owner',
  display_role: 'owner',
  permissions: { 'platform.access': true },
  is_platform_superuser: true,
})

assert.equal(system.context_type, 'system')
assert.equal(system.active_household_id, '0')
assert.equal(system.role, 'owner')
assert.equal(system.display_role, 'owner')
assert.equal(system.permissions['platform.access'], true)
assert.equal(system.is_platform_superuser, true)

const unprivilegedSystem = storeAuthContext({
  user_id: 'system-user-without-platform-rights',
  context_type: 'system',
  active_household_id: '0',
  role: 'member',
  permissions: {},
  is_platform_superuser: false,
})

assert.equal(unprivilegedSystem.context_type, 'system')
assert.deepEqual(unprivilegedSystem.permissions, {})
assert.equal(unprivilegedSystem.is_platform_superuser, false)

clearAuthSession()
assert.equal(readStoredAuthContext(), null)

console.log('SESSION_CONTEXT_NORMALIZATION_CONTRACT_GREEN')
