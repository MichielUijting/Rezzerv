import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import { fetchJsonWithAuth, readStoredAuthContext, isHouseholdViewerFromContext } from '../../lib/authSession.js'

const tiles = [
  { key: 'meldingen', label: 'Meldingen', icon: '✉️' },
  { key: 'bijna-op', label: 'Bijna op', icon: '📉' },
  { key: 'winkelen', label: 'Winkelen', icon: '🛒' },
  { key: 'prognoses', label: 'Prognoses', icon: '📊' },
  { key: 'uitlenen', label: 'Uitlenen', icon: '🔁' },
  { key: 'voorraad', label: 'Voorraad', icon: '📦' },
  { key: 'productgroepen', label: 'Productgroepen', icon: '🧩' },
  { key: 'kassabonnen', label: 'Uitpakken', icon: '🧾' },
  { key: 'kassa', label: 'Kassa', icon: '🧾' },
  { key: 'spaartegoeden', label: 'Spaartegoeden', icon: '🪙' },
  { key: 'externe-databases', label: 'Externe databases', icon: '🗄️' },
  { key: 'catalogus', label: 'Catalogus', icon: 'CAT' },
  { key: 'klantkaarten', label: 'Klantkaarten', icon: '💳' },
  { key: 'recepten', label: 'Recepten', icon: '🍳' },
  { key: 'bestellen', label: 'Bestellen', icon: '📋' },
  { key: 'verlengen', label: 'Verlengen', icon: '⏳' },
  { key: 'instellingen', label: 'Instellingen', icon: '⚙️' },
  { key: 'admin', label: 'Admin', icon: '🛠️' },
]

const ADMIN_ROLES = new Set(['admin', 'owner', 'household.admin', 'huishoudbeheerder'])
const PLATFORM_TILE_PERMISSIONS = {
  'externe-databases': 'platform.external_databases.view',
  catalogus: 'platform.catalog.view',
  admin: 'platform.users.view',
}

function isActiveHouseholdAdmin(context) {
  const activeId = String(context?.active_household_id || '').trim()
  const membership = (Array.isArray(context?.memberships) ? context.memberships : []).find((item) => {
    const membershipId = String(item?.household_id || item?.id || '').trim()
    return activeId && membershipId === activeId
  })
  const membershipRole = String(membership?.role || membership?.membership_role || '').trim().toLowerCase()
  const displayRole = String(context?.display_role || '').trim().toLowerCase()
  return ADMIN_ROLES.has(membershipRole) || ADMIN_ROLES.has(displayRole)
}

async function hasPlatformPermission(permissionKey) {
  try {
    const response = await fetchJsonWithAuth(`/api/platform/toegang?bevoegdheid=${encodeURIComponent(permissionKey)}`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) return false
    const data = await response.json().catch(() => ({}))
    return data?.toegang === true
  } catch {
    return false
  }
}

export default function HomePage() {
  const navigate = useNavigate()
  const storedContext = readStoredAuthContext()
  const contextConfirmsHouseholdAdmin = isActiveHouseholdAdmin(storedContext)
  const [householdName, setHouseholdName] = useState(storedContext?.active_household_name || '')
  const [isHouseholdAdmin, setIsHouseholdAdmin] = useState(contextConfirmsHouseholdAdmin)
  const [isViewer, setIsViewer] = useState(isHouseholdViewerFromContext(storedContext))
  const [platformTiles, setPlatformTiles] = useState({
    'externe-databases': false,
    catalogus: false,
    admin: false,
  })

  useEffect(() => {
    let active = true
    const token = localStorage.getItem('rezzerv_token')
    if (!token) return undefined

    fetch('/api/household', { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' })
      .then(async (res) => { if (!res.ok) throw new Error('Huishouden niet beschikbaar'); return res.json() })
      .then((data) => {
        if (!active) return
        const name = data?.naam || 'Mijn huishouden'
        setHouseholdName(name)
        setIsHouseholdAdmin(contextConfirmsHouseholdAdmin || Boolean(data?.is_household_admin))
        setIsViewer(Boolean(data?.is_viewer))
        localStorage.setItem('rezzerv_household_name', name)
      }).catch(() => {})

    Promise.all(
      Object.entries(PLATFORM_TILE_PERMISSIONS).map(async ([key, permissionKey]) => [key, await hasPlatformPermission(permissionKey)]),
    ).then((entries) => {
      if (active) setPlatformTiles(Object.fromEntries(entries))
    })

    return () => { active = false }
  }, [contextConfirmsHouseholdAdmin])

  function openTile(key) {
    if (key === 'meldingen') navigate('/meldingen')
    if (key === 'bijna-op') navigate('/bijna-op')
    if (key === 'voorraad') navigate('/voorraad')
    if (key === 'productgroepen') navigate('/productgroepen')
    if (key === 'kassabonnen') navigate('/kassabonnen')
    if (key === 'kassa') navigate('/kassa')
    if (key === 'spaartegoeden') navigate('/spaartegoeden')
    if (key === 'externe-databases') navigate('/externe-databases')
    if (key === 'catalogus') navigate('/catalogus')
    if (key === 'instellingen') navigate('/instellingen')
    if (key === 'admin') navigate('/admin')
  }

  const visibleTiles = tiles.filter((tile) => {
    if (tile.key === 'meldingen') return isHouseholdAdmin
    if (Object.hasOwn(PLATFORM_TILE_PERMISSIONS, tile.key)) return Boolean(platformTiles[tile.key])
    return true
  })

  return <div className="rz-screen"><Header title="Startpagina"/><div className="rz-content"><div className="rz-content-inner"><Card className="rz-card-home"><div className="rz-tile-grid" role="navigation" aria-label="Acties">{visibleTiles.map((t)=>{const clickable=['meldingen','bijna-op','voorraad','productgroepen','kassabonnen','kassa','spaartegoeden','externe-databases','instellingen','admin','catalogus'].includes(t.key);return <div key={t.key} className="rz-tile" onClick={()=>clickable&&openTile(t.key)} style={{cursor:clickable?'pointer':'default'}}><div className="rz-tile-icon" aria-hidden="true">{t.icon}</div><div className="rz-tile-label">{t.label}</div></div>})}</div></Card></div></div></div>
}
