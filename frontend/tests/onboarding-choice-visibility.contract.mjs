import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

function read(relativePath) {
  return fs.readFileSync(new URL(`../${relativePath}`, import.meta.url), 'utf8')
}

function sourceFiles(directory) {
  const result = []
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name)
    if (entry.isDirectory()) result.push(...sourceFiles(target))
    else if (/\.(?:css|jsx?|tsx?)$/i.test(entry.name)) result.push(target)
  }
  return result
}

const login = read('src/features/auth/LoginPage.jsx')
const controls = read('src/features/onboarding/OnboardingChoiceControls.jsx')
const onboarding = read('src/features/onboarding/OnboardingPage.jsx')
const inhuis = read('src/features/onboarding/InhuisHalenOnboardingPage.jsx')
const wat = read('src/features/onboarding/WatInhuisOnboardingPage.jsx')
const waar = read('src/features/onboarding/WaarInhuisOnboardingPage.jsx')
const shared = read('src/features/onboarding/SharedHouseholdMinimumPage.jsx')
const settings = read('src/features/settings/SettingsPage.jsx')
const invitationService = read('src/features/settings/services/householdInvitationsService.js')
const formControls = read('src/ui/form-controls.css')
const checkboxComponent = read('src/ui/Checkbox.jsx')
const main = read('src/main.jsx')
const tokens = read('src/ui/tokens.css')

const srcRoot = fileURLToPath(new URL('../src', import.meta.url))
const nonCanonicalAccents = []
for (const file of sourceFiles(srcRoot)) {
  const content = fs.readFileSync(file, 'utf8')
  const relative = path.relative(srcRoot, file).replaceAll('\\', '/')

  for (const match of content.matchAll(/accent-color\s*:\s*([^;}\n]+)/gi)) {
    const value = String(match[1] || '').trim()
    if (value !== 'var(--color-brand-primary)') nonCanonicalAccents.push(`${relative}: accent-color ${value}`)
  }

  for (const match of content.matchAll(/accentColor\s*:\s*['"]([^'"]+)['"]/g)) {
    const value = String(match[1] || '').trim()
    if (value !== 'var(--color-brand-primary)') nonCanonicalAccents.push(`${relative}: accentColor ${value}`)
  }
}

const checks = [
  [login.includes('const [showPassword, setShowPassword] = useState(false)'), 'login stores show-password choice'],
  [login.includes("type={showPassword ? 'text' : 'password'}"), 'login password visibility changes input type'],
  [login.includes('data-testid="login-show-password"'), 'login exposes password visibility checkbox'],
  [controls.includes('type="radio"'), 'onboarding uses native radio controls'],
  [controls.includes('type="checkbox"'), 'onboarding supports native checkbox controls'],
  [controls.includes("title = 'Jouw keuzes'"), 'onboarding has reusable visible choice summary'],
  [onboarding.includes('data-testid="onboarding-primary-continue"'), 'primary use case is confirmed explicitly'],
  [onboarding.includes('De keuze wordt pas opgeslagen als je op Verder drukt.'), 'primary choice remains changeable before confirmation'],
  [onboarding.includes('Je kunt vóór Verder altijd een andere radioknop kiezen.'), 'primary choice can be revised before save'],
  [onboarding.includes('Welkom bij Inhuis · ${primaryUseCaseTitle}'), 'selected primary use case is visible in header'],
  [inhuis.includes('<ChoiceSummary'), 'Inhuis halen shows live selected settings'],
  [wat.includes('<ChoiceSummary'), 'Wat Inhuis shows live selected settings'],
  [waar.includes('<ChoiceSummary'), 'Waar Inhuis shows live selected settings'],
  [waar.includes('<CheckboxChoice'), 'Waar Inhuis location choices are checkboxes'],
  [shared.includes('title="Jouw volledige inrichting"'), 'final household step reviews the complete setup'],
  [shared.includes('createHouseholdInvitation'), 'Samen reuses canonical invitation service'],
  [shared.includes('revokeHouseholdInvitation'), 'switching from Samen to Alleen can revoke invitations made in onboarding'],
  [shared.includes('onboardingInvitations'), 'onboarding tracks invitations created before final household choice'],
  [shared.includes('data-testid="shared-household-invite-email"'), 'Samen shows invitation email input immediately'],
  [shared.includes('data-testid="shared-household-invite-send"'), 'Samen can send invitation immediately'],
  [!shared.includes('shared-household-invite-deferred'), 'deferred invitation placeholder is removed'],
  [invitationService.includes("'/api/household/invitations'"), 'immediate invite uses existing secured household invitation endpoint'],
  [invitationService.includes('/revoke`'), 'canonical invitation service exposes revocation used by onboarding'],
  [settings.includes('data-testid="settings-active-profile"'), 'completed household keeps active profile visible in Settings'],
  [settings.includes('Jouw Inhuis'), 'Settings labels persistent active profile clearly'],
  [settings.includes('buildActiveProfileItems'), 'Settings derives visible profile from authoritative onboarding product configuration'],
  [tokens.includes('--color-brand-primary: #1A3E2B;'), 'canonical Rezzerv primary color token remains defined'],
  [main.includes('import "./ui/form-controls.css";'), 'global native form-control branding is loaded'],
  [formControls.includes("input[type='checkbox']") && formControls.includes("input[type='radio']"), 'global branding covers native checkboxes and radios'],
  [formControls.includes('accent-color: var(--color-brand-primary);'), 'native selected state uses Rezzerv primary color'],
  [formControls.includes("input[type='checkbox']:focus-visible") && formControls.includes("input[type='radio']:focus-visible"), 'keyboard focus branding covers checkboxes and radios'],
  [formControls.includes('outline: 2px solid var(--color-brand-primary);'), 'native focus ring uses Rezzerv primary color'],
  [checkboxComponent.includes("accentColor: 'var(--color-brand-primary)'"), 'shared Checkbox component uses canonical brand token'],
  [nonCanonicalAccents.length === 0, `all frontend accent declarations use Rezzerv token${nonCanonicalAccents.length ? `: ${nonCanonicalAccents.join(', ')}` : ''}`],
]

for (const [ok, label] of checks) {
  if (!ok) throw new Error(`FAIL ${label}`)
  console.log(`PASS ${label}`)
}

console.log('ONBOARDING_VISIBLE_CHOICES_FRONTEND_CONTRACT_GREEN')
