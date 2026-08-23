import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import {
  canCurrentUserPerform,
  fetchAuthContext,
  isFrontteamMemberFromContext,
  isHouseholdAdminFromContext,
  isPlatformSuperuserFromContext,
  logoutServerSession,
  readStoredAuthContext,
} from '../../lib/authSession.js'
import {
  fetchHouseholdOnboarding,
  readHouseholdOnboarding,
} from '../onboarding/onboardingState.js'
import { buildHomeNavigation } from './homeNavigation.js'

function visibilityFromContext(context) {
  return {
    canOpenAdmin: isHouseholdAdminFromContext(context),
    canOpenExternalDatabases: isFrontteamMemberFromContext(context),
    isPlatformSuperuser: isPlatformSuperuserFromContext(context),
    canManageLocations: canCurrentUserPerform('locations.manage', context),
  }
}

const TILE_ROUTES = {
  meldingen: '/meldingen',
  'bijna-op': '/bijna-op',
  winkelen: '/winkelen',
  voorraad: '/voorraad',
  productgroepen: '/productgroepen',
  kassabonnen: '/kassabonnen',
  kassa: '/kassa',
  spaartegoeden: '/spaartegoeden',
  'externe-databases': '/externe-databases',
  catalogus: '/catalogus',
  instellingen: '/instellingen',
  locaties: '/instellingen/locaties',
  admin: '/admin',
  superuser: '/superuser',
}

export default function HomePage() {
  const navigate = useNavigate()
  const initialContext = readStoredAuthContext()
  const [context, setContext] = useState(initialContext)
  const [onboarding, setOnboarding] = useState(() => readHouseholdOnboarding(initialContext))
  const [showMore, setShowMore] = useState(false)
  const visibility = visibilityFromContext(context)
  const navigation = buildHomeNavigation({ onboarding, visibility })

  useEffect(() => {
    let cancelled = false

    async function refreshHomeContext() {
      try {
        const nextContext = await fetchAuthContext()
        if (cancelled) return
        setContext(nextContext)

        if (nextContext?.context_type === 'regular') {
          const nextOnboarding = await fetchHouseholdOnboarding(nextContext, { force: true })
          if (!cancelled) setOnboarding(nextOnboarding)
        } else if (!cancelled) {
          setOnboarding(null)
        }
      } catch {
        // AuthGuard remains authoritative for session failures.
      }
    }

    refreshHomeContext()
    return () => {
      cancelled = true
    }
  }, [])

  async function logout() {
    await logoutServerSession()
    navigate('/login', { replace: true })
  }

  if (context?.context_type === 'none') {
    return (
      <div className="rz-screen" data-testid="none-session-home">
        <Header title="Platformbeheerder" />
        <div className="rz-content">
          <div className="rz-content-inner">
            <Card className="rz-card-home">
              <h2>Platformbeheerder</h2>
              <p>Er is geen huishoudcontext actief.</p>
              <Button type="button" variant="secondary" onClick={logout} data-testid="none-session-logout">
                Uitloggen
              </Button>
            </Card>
          </div>
        </div>
      </div>
    )
  }

  function openTile(tile) {
    const route = TILE_ROUTES[tile.key]
    if (tile.clickable && route) navigate(route)
  }

  function renderTile(tile) {
    const route = TILE_ROUTES[tile.key]
    const clickable = Boolean(tile.clickable && route)
    return (
      <div
        key={tile.key}
        className="rz-tile"
        data-testid={`home-tile-${tile.key}`}
        onClick={() => clickable && openTile(tile)}
        style={{ cursor: clickable ? 'pointer' : 'default' }}
      >
        <div className="rz-tile-icon" aria-hidden="true">{tile.icon}</div>
        <div className="rz-tile-label">{tile.label}</div>
      </div>
    )
  }

  return (
    <div className="rz-screen">
      <Header title="Startpagina" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-home">
            {navigation.mode === 'legacy' ? (
              <div
                className="rz-tile-grid"
                role="navigation"
                aria-label="Acties"
                data-testid="legacy-home-navigation"
              >
                {navigation.primaryTiles.map(renderTile)}
              </div>
            ) : (
              <div data-testid="dynamic-home-navigation">
                <h2 style={{ margin: '0 0 14px 0', fontSize: '20px' }}>Voor jou</h2>
                <div className="rz-tile-grid" role="navigation" aria-label="Belangrijkste acties">
                  {navigation.primaryTiles.map(renderTile)}
                </div>

                {navigation.moreTiles.length > 0 && (
                  <div style={{ marginTop: '20px' }}>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => setShowMore((current) => !current)}
                      data-testid="home-more-toggle"
                    >
                      {showMore ? 'Minder tonen' : 'Meer'}
                    </Button>
                    {showMore && (
                      <div
                        className="rz-tile-grid"
                        role="navigation"
                        aria-label="Meer acties"
                        data-testid="home-more-navigation"
                        style={{ marginTop: '14px' }}
                      >
                        {navigation.moreTiles.map(renderTile)}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
