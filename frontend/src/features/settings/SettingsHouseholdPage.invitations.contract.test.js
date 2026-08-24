import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const settingsRoot = path.resolve(process.cwd(), 'src/features/settings')
const pageSource = fs.readFileSync(path.join(settingsRoot, 'SettingsHouseholdPage.jsx'), 'utf8')
const memberServiceSource = fs.readFileSync(path.join(settingsRoot, 'services/householdMembersService.js'), 'utf8')
const invitationServiceSource = fs.readFileSync(path.join(settingsRoot, 'services/householdInvitationsService.js'), 'utf8')

const checks = [
  ['invitation_heading', pageSource.includes('Huishoudlid uitnodigen')],
  ['email_only_copy', pageSource.includes('Vul alleen het e-mailadres in.')],
  ['invitation_submit', pageSource.includes('Uitnodiging versturen')],
  ['pending_label', pageSource.includes("pending: 'In afwachting'")],
  ['accepted_label', pageSource.includes("accepted: 'Geaccepteerd'")],
  ['expired_label', pageSource.includes("expired: 'Verlopen'")],
  ['revoked_label', pageSource.includes("revoked: 'Ingetrokken'")],
  ['resend_action', pageSource.includes('Opnieuw versturen')],
  ['revoke_action', pageSource.includes('Intrekken')],
  ['delivery_disabled_message', pageSource.includes('E-mailverzending is nog niet geactiveerd.')],
  ['uses_invitation_service', pageSource.includes("from './services/householdInvitationsService'")],
  ['no_old_create_member_import', !pageSource.includes('createHouseholdMember')],
  ['no_old_heading', !pageSource.includes('Nieuw huishoudlid koppelen')],
  ['no_old_submit', !pageSource.includes('Lid koppelen')],
  ['no_password_input', !pageSource.includes('household-member-password-input') && !pageSource.includes('label="Wachtwoord"')],
  ['member_service_has_no_create_post', !memberServiceSource.includes('createHouseholdMember') && !memberServiceSource.includes("method: 'POST'")],
  ['invitation_create_endpoint', invitationServiceSource.includes("fetchJsonWithAuth('/api/household/invitations'") && invitationServiceSource.includes("method: 'POST'")],
  ['invitation_list_endpoint', invitationServiceSource.includes('fetchHouseholdInvitations')],
  ['invitation_resend_endpoint', invitationServiceSource.includes('/resend')],
  ['invitation_revoke_endpoint', invitationServiceSource.includes('/revoke')],
]

const failed = checks.filter(([, ok]) => !ok)
for (const [name, ok] of checks) {
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}`)
}

if (failed.length > 0) {
  console.error(`RESULT ${checks.length - failed.length}/${checks.length} checks passed`)
  process.exit(1)
}

console.log(`RESULT ${checks.length}/${checks.length} checks passed`)
console.log('HOUSEHOLD_INVITATION_UI_CONTRACT_GREEN')
