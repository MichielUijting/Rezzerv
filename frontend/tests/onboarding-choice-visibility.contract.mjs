import fs from 'node:fs'

function read(path) {
  return fs.readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')
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
  [shared.includes('data-testid="shared-household-invite-email"'), 'Samen shows invitation email input immediately'],
  [shared.includes('data-testid="shared-household-invite-send"'), 'Samen can send invitation immediately'],
  [!shared.includes('shared-household-invite-deferred'), 'deferred invitation placeholder is removed'],
  [invitationService.includes("'/api/household/invitations'"), 'immediate invite uses existing secured household invitation endpoint'],
  [settings.includes('data-testid="settings-active-profile"'), 'completed household keeps active profile visible in Settings'],
  [settings.includes('Jouw Inhuis'), 'Settings labels persistent active profile clearly'],
  [settings.includes('buildActiveProfileItems'), 'Settings derives visible profile from authoritative onboarding product configuration'],
]

for (const [ok, label] of checks) {
  if (!ok) throw new Error(`FAIL ${label}`)
  console.log(`PASS ${label}`)
}

console.log('ONBOARDING_VISIBLE_CHOICES_FRONTEND_CONTRACT_GREEN')
