const REGULAR_MEMBER_ROLES = new Set([
  'lid',
  'member',
  'household.member',
])

const REGULAR_ADMIN_ROLES = new Set([
  'admin',
  'beheerder',
  'owner',
  'household.admin',
  'household.owner',
])

const SPECIAL_PLATFORM_PERMISSIONS = new Set([
  'frontteam.external_databases.access',
  'platform.feature_flags.manage',
  'platform.functional_features.manage',
  'platform.special_roles.manage',
  'platform.technical_configuration.manage',
])

function normalizeRole(value) {
  return String(value || '').trim().toLowerCase()
}

function hasSpecialPlatformPermission(context) {
  const permissions = context?.permissions && typeof context.permissions === 'object'
    ? context.permissions
    : {}
  return [...SPECIAL_PLATFORM_PERMISSIONS].some((permission) => Boolean(permissions[permission]))
}

export function isMobileInventoryEligibleContext(context) {
  if (!context || context.context_type !== 'regular') return false
  if (context.is_frontteam || context.is_platform_superuser) return false
  if (hasSpecialPlatformPermission(context)) return false

  const role = normalizeRole(context.display_role || context.role)
  return REGULAR_MEMBER_ROLES.has(role) || REGULAR_ADMIN_ROLES.has(role)
}

export function isMobileInventoryViewport(mediaQueryList) {
  return Boolean(mediaQueryList?.matches)
}

export const MOBILE_INVENTORY_MEDIA_QUERY = '(max-width: 720px)'
