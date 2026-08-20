import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { fetchAuthorizationOverview } from './services/authorizationMembershipService'
import './settingsAuthorization.css'

const ROLE_LABELS = {
  'household.member': 'Lid',
  'household.admin': 'Beheerder',
  'household.owner': 'Superuser',
  'household.frontteam': 'Frontteamlid',
}

const AUTHORIZATION_ROLE_KEYS = new Set([
  'household.member',
  'household.admin',
  'household.owner',
  'household.frontteam',
])

const AUTHORIZATION_ROWS = [
  ['dashboard.view', 'Startscherm bekijken'],
  ['notifications.update', 'Meldingen afhandelen'],
  ['inventory.view', 'Voorraad bekijken'],
  ['inventory.update', 'Voorraad wijzigen'],
  ['inventory.correct', 'Voorraad corrigeren'],
  ['receipts.view', 'Kassabonnen bekijken'],
  ['receipts.process', 'Kassabonnen verwerken'],
  ['receipts.delete', 'Kassabonnen verwijderen'],
  ['unpacking.view', 'Uitpakken bekijken'],
  ['unpacking.process', 'Artikelen uitpakken'],
  ['unpacking.correct', 'Uitpakhandelingen corrigeren'],
  ['almost_out.view', 'Bijna op bekijken'],
  ['almost_out.update', 'Bijna op wijzigen'],
  ['shopping_list.view', 'Inkooplijst bekijken'],
  ['shopping_list.update', 'Inkooplijst wijzigen'],
  ['shopping_list.manage', 'Inkooplijst beheren'],
  ['articles.view', 'Artikelen bekijken'],
  ['articles.update', 'Artikelen wijzigen'],
  ['articles.manage', 'Artikelen beheren'],
  ['article_groups.view', 'Artikelgroepen bekijken'],
  ['article_groups.assign', 'Artikelgroepen toekennen'],
  ['article_groups.manage', 'Artikelgroepen beheren'],
  ['locations.view', 'Locaties bekijken'],
  ['locations.update', 'Locaties wijzigen'],
  ['locations.manage', 'Locaties beheren'],
  ['stores.view', 'Winkels bekijken'],
  ['stores.update', 'Winkels wijzigen'],
  ['stores.manage', 'Winkels beheren'],
  ['loyalty.view', 'Spaartegoeden bekijken'],
  ['loyalty.update', 'Spaartegoeden wijzigen'],
  ['loyalty.manage', 'Spaartegoeden beheren'],
  ['insights.view', 'Inzichten en prognoses bekijken'],
  ['insights.export', 'Inzichten en prognoses exporteren'],
  ['members.view', 'Huishoudleden bekijken'],
  ['members.manage', 'Huishoudleden en rollen beheren'],
  ['household_settings.view', 'Huishoudinstellingen bekijken'],
  ['household_settings.manage', 'Huishoudinstellingen beheren'],
  ['permissions.view', 'Autorisaties bekijken'],
  ['permissions.manage', 'Individuele autorisaties beheren'],
  ['catalog.view', 'Catalogus bekijken'],
  ['catalog.update', 'Catalogus wijzigen'],
  ['catalog.manage', 'Catalogus beheren'],
  ['gpc.view', 'Productclassificatie bekijken'],
  ['gpc.update', 'Productclassificatie wijzigen'],
  ['gpc.manage', 'Productclassificatie beheren'],
]

export default function SettingsAuthorizationPage() {
  const { showFeedback } = useAppFeedback()
  const [overview, setOverview] = useState({ roles: [], permissions: [] })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    async function load() {
      setLoading(true)
      try {
        const payload = await fetchAuthorizationOverview()
        if (active) setOverview(payload)
      } catch (error) {
        if (active) {
          showFeedback({
            variant: 'error',
            title: 'Autorisaties niet geladen',
            message: error?.message || 'De autorisaties konden niet worden geladen.',
          })
        }
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [showFeedback])

  const roleColumns = useMemo(
    () => overview.roles.filter((role) => AUTHORIZATION_ROLE_KEYS.has(role.role_key)).map((role) => ({
      ...role,
      label: ROLE_LABELS[role.role_key] || role.name,
      granted: new Set(role.permission_keys || []),
    })),
    [overview.roles],
  )

  const availablePermissions = useMemo(
    () => new Set(overview.permissions.map((permission) => permission.permission_key)),
    [overview.permissions],
  )

  const rows = useMemo(
    () => AUTHORIZATION_ROWS.filter(([permissionKey]) => availablePermissions.has(permissionKey)),
    [availablePermissions],
  )

  return (
    <AppShell title="Instellingen" showExit={false}>
      <div className="rz-authorization-page" data-testid="authorization-settings-page">
        <Card>
          <div className="rz-authorization-header">
            <h2>Autorisaties</h2>
            <p>Bekijk per rol welke mogelijkheden binnen het huishouden beschikbaar zijn.</p>
          </div>

          {loading ? <div className="rz-authorization-loading">Autorisaties laden…</div> : (
            <>
              <p className="rz-authorization-explanation">
                De rollen zijn vaste profielen. Wijs een rol aan een huishoudlid toe in het scherm Huishouden.
              </p>
              <div className="rz-authorization-matrix-wrap">
                <table className="rz-authorization-matrix" data-testid="authorization-role-matrix">
                  <thead>
                    <tr>
                      <th scope="col">Autorisatie</th>
                      {roleColumns.map((role) => <th scope="col" key={role.role_key}>{role.label}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map(([permissionKey, label]) => (
                      <tr key={permissionKey}>
                        <th scope="row">{label}</th>
                        {roleColumns.map((role) => {
                          const granted = role.granted.has(permissionKey)
                          return (
                            <td key={role.role_key}>
                              <input
                                type="checkbox"
                                checked={granted}
                                readOnly
                                aria-readonly="true"
                                aria-label={`${label} voor ${role.label}: ${granted ? 'toegestaan' : 'niet toegestaan'}`}
                                onClick={(event) => event.preventDefault()}
                              />
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </Card>
      </div>
    </AppShell>
  )
}
