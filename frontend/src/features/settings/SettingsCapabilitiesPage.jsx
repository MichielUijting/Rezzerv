import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import { readStoredAuthContext } from '../../lib/authSession.js'
import { fetchHouseholdOnboarding } from '../onboarding/onboardingState.js'
import {
  CAPABILITY_USE_CASES,
  buildExpansionQuestions,
  isUseCaseActive,
} from './capabilityExpansion.js'

const EMPTY_FORM = {
  simpleInventory: true,
  almostOutNotifications: false,
  receiptProcessing: false,
  recipes: false,
  inventoryLevel: 'presence',
  globalLocations: false,
  almostOut: false,
  shopping: false,
  unpacking: false,
  mainLocations: [''],
  sublocations: [],
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: 'include',
    cache: 'no-store',
    ...options,
    headers: {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(payload?.detail || 'Inhuis uitbreiden mislukt.')
    error.status = response.status
    throw error
  }
  return payload
}

function checkbox(label, checked, onChange, testId, disabled = false) {
  return (
    <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', color: '#344054' }}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        data-testid={testId}
        disabled={disabled}
        style={{ marginTop: 3 }}
      />
      <span>{label}</span>
    </label>
  )
}

export default function SettingsCapabilitiesPage() {
  const context = readStoredAuthContext()
  const [state, setState] = useState(null)
  const [selectedUseCase, setSelectedUseCase] = useState('')
  const [form, setForm] = useState(EMPTY_FORM)
  const [existingSpaces, setExistingSpaces] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const configuration = state?.product_configuration || null
  const questions = useMemo(
    () => buildExpansionQuestions(selectedUseCase, configuration),
    [selectedUseCase, configuration],
  )

  async function loadCapabilities() {
    setIsLoading(true)
    setError('')
    try {
      const next = await requestJson('/api/onboarding/capabilities')
      setState(next)
    } catch (loadError) {
      setError(loadError?.message || 'Mogelijkheden konden niet worden geladen.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadCapabilities()
  }, [])

  useEffect(() => {
    if (selectedUseCase !== 'waar_inhuis' || !questions.locationRefinement) return
    let cancelled = false
    requestJson('/api/spaces')
      .then((payload) => {
        if (cancelled) return
        setExistingSpaces(Array.isArray(payload?.items) ? payload.items.filter((item) => item?.active !== false) : [])
      })
      .catch(() => {
        if (!cancelled) setExistingSpaces([])
      })
    return () => { cancelled = true }
  }, [selectedUseCase, questions.locationRefinement])

  function chooseUseCase(useCase) {
    setError('')
    setMessage('')
    setSelectedUseCase(useCase)
    setForm({ ...EMPTY_FORM, mainLocations: [''], sublocations: [] })
  }

  function updateMainLocation(index, value) {
    setForm((current) => ({
      ...current,
      mainLocations: current.mainLocations.map((item, itemIndex) => itemIndex === index ? value : item),
    }))
  }

  function addMainLocation() {
    setForm((current) => ({ ...current, mainLocations: [...current.mainLocations, ''] }))
  }

  function addSublocation() {
    const firstSpaceName = String(existingSpaces[0]?.naam || form.mainLocations.find((item) => item.trim()) || '')
    setForm((current) => ({
      ...current,
      sublocations: [...current.sublocations, { space_name: firstSpaceName, name: '' }],
    }))
  }

  function updateSublocation(index, patch) {
    setForm((current) => ({
      ...current,
      sublocations: current.sublocations.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item),
    }))
  }

  async function submitExpansion() {
    if (!selectedUseCase) return
    setIsSaving(true)
    setError('')
    setMessage('')
    try {
      let url = ''
      let payload = {}
      if (selectedUseCase === 'inhuis_halen') {
        url = '/api/onboarding/expand/inhuis-halen'
        payload = {
          simple_inventory_enabled: questions.inventoryUpgrade ? form.simpleInventory : false,
          almost_out_notifications_enabled: questions.almostOutNotifications ? form.almostOutNotifications : false,
          receipt_processing_enabled: questions.receiptProcessing ? form.receiptProcessing : false,
          recipes_enabled: questions.recipes ? form.recipes : false,
        }
      } else if (selectedUseCase === 'wat_inhuis') {
        url = '/api/onboarding/expand/wat-inhuis'
        payload = {
          inventory_tracking_level: questions.inventoryLevel ? form.inventoryLevel : null,
          global_locations_enabled: questions.globalLocations ? form.globalLocations : false,
          almost_out_enabled: questions.almostOut ? form.almostOut : false,
          shopping_enabled: questions.shopping ? form.shopping : false,
        }
      } else {
        url = '/api/onboarding/expand/waar-inhuis'
        const mainLocations = questions.locationRefinement
          ? form.mainLocations.map((item) => item.trim()).filter(Boolean)
          : []
        const sublocations = questions.locationRefinement
          ? form.sublocations
            .map((item) => ({ space_name: item.space_name.trim(), name: item.name.trim() }))
            .filter((item) => item.space_name && item.name)
          : []
        payload = {
          main_locations: mainLocations,
          sublocations,
          unpacking_enabled: questions.unpacking ? form.unpacking : false,
          receipt_processing_enabled: questions.receiptProcessing ? form.receiptProcessing : false,
          almost_out_enabled: questions.almostOut ? form.almostOut : false,
        }
      }

      const next = await requestJson(url, { method: 'POST', body: JSON.stringify(payload) })
      setState(next)
      setSelectedUseCase('')
      setMessage('Mogelijkheid toegevoegd. Home en Instellingen passen zich direct aan.')
      if (context?.context_type === 'regular') {
        await fetchHouseholdOnboarding(context, { force: true })
      }
    } catch (saveError) {
      setError(saveError?.message || 'Inhuis uitbreiden mislukt.')
    } finally {
      setIsSaving(false)
    }
  }

  const availableParentNames = [
    ...existingSpaces.map((item) => String(item?.naam || '').trim()).filter(Boolean),
    ...form.mainLocations.map((item) => item.trim()).filter(Boolean),
  ].filter((value, index, array) => array.indexOf(value) === index)

  function renderExpansionForm() {
    if (!selectedUseCase) return null
    const selected = CAPABILITY_USE_CASES.find((item) => item.key === selectedUseCase)
    if (!selected) return null

    return (
      <Card>
        <div style={{ display: 'grid', gap: 16 }} data-testid={`capability-expansion-form-${selectedUseCase}`}>
          <div>
            <h3 style={{ margin: '0 0 6px 0' }}>{selected.title} toevoegen</h3>
            <p style={{ margin: 0, color: '#667085' }}>We vragen alleen wat nog niet uit de huidige inrichting bekend is.</p>
          </div>

          {selectedUseCase === 'inhuis_halen' && (
            <>
              <div style={{ color: '#475467' }}>Winkelen wordt automatisch toegevoegd.</div>
              {questions.inventoryUpgrade && checkbox('Eenvoudige voorraad met aantallen gebruiken', form.simpleInventory, (value) => setForm((current) => ({ ...current, simpleInventory: value, almostOutNotifications: value ? current.almostOutNotifications : false })), 'capability-inhuis-simple-inventory')}
              {questions.almostOutNotifications && checkbox('Meldingen krijgen wanneer iets bijna op is', form.almostOutNotifications, (value) => setForm((current) => ({ ...current, almostOutNotifications: value })), 'capability-inhuis-notifications', configuration?.inventory_tracking_level === 'none' && !form.simpleInventory)}
              {questions.receiptProcessing && checkbox('Kassabonnen nu verwerken', form.receiptProcessing, (value) => setForm((current) => ({ ...current, receiptProcessing: value })), 'capability-inhuis-receipts')}
              {questions.recipes && checkbox('Gerechten/Recepten alvast activeren', form.recipes, (value) => setForm((current) => ({ ...current, recipes: value })), 'capability-inhuis-recipes')}
            </>
          )}

          {selectedUseCase === 'wat_inhuis' && (
            <>
              {questions.inventoryLevel && (
                <label style={{ display: 'grid', gap: 6 }}>
                  <span style={{ fontWeight: 600 }}>Hoe wil je bijhouden wat Inhuis is?</span>
                  <select value={form.inventoryLevel} onChange={(event) => setForm((current) => ({ ...current, inventoryLevel: event.target.value }))} data-testid="capability-wat-inventory-level">
                    <option value="presence">Alleen aanwezigheid</option>
                    <option value="quantity">Aantallen</option>
                  </select>
                </label>
              )}
              {questions.globalLocations && checkbox('Ook hoofdlocaties bijhouden', form.globalLocations, (value) => setForm((current) => ({ ...current, globalLocations: value })), 'capability-wat-global-locations')}
              {questions.almostOut && checkbox('Bijna op gebruiken', form.almostOut, (value) => setForm((current) => ({ ...current, almostOut: value })), 'capability-wat-almost-out')}
              {questions.shopping && checkbox('Winkelen gebruiken', form.shopping, (value) => setForm((current) => ({ ...current, shopping: value })), 'capability-wat-shopping')}
            </>
          )}

          {selectedUseCase === 'waar_inhuis' && (
            <>
              {questions.preserveGlobalLocations && existingSpaces.length > 0 && (
                <div style={{ padding: 12, border: '1px solid #dfe4ea', borderRadius: 10 }} data-testid="capability-preserved-global-locations">
                  <strong>Bestaande hoofdlocaties blijven behouden:</strong> {existingSpaces.map((item) => item.naam).join(', ')}.
                </div>
              )}
              {questions.locationRefinement && (
                <div style={{ display: 'grid', gap: 10 }}>
                  <div style={{ fontWeight: 600 }}>{questions.needsFirstMainLocation ? 'Voeg minimaal één hoofdlocatie toe' : 'Extra hoofdlocatie toevoegen (optioneel)'}</div>
                  {form.mainLocations.map((value, index) => (
                    <input
                      key={index}
                      value={value}
                      onChange={(event) => updateMainLocation(index, event.target.value)}
                      placeholder="Bijvoorbeeld: Keuken"
                      data-testid={`capability-waar-main-location-${index}`}
                    />
                  ))}
                  <div><Button type="button" variant="secondary" onClick={addMainLocation}>Nog een hoofdlocatie</Button></div>
                  {availableParentNames.length > 0 && (
                    <>
                      <div style={{ fontWeight: 600, marginTop: 4 }}>Sublocaties verfijnen (optioneel)</div>
                      {form.sublocations.map((item, index) => (
                        <div key={index} style={{ display: 'grid', gridTemplateColumns: 'minmax(140px, 1fr) minmax(160px, 1fr)', gap: 10 }}>
                          <select value={item.space_name} onChange={(event) => updateSublocation(index, { space_name: event.target.value })}>
                            <option value="">Kies hoofdlocatie</option>
                            {availableParentNames.map((name) => <option key={name} value={name}>{name}</option>)}
                          </select>
                          <input value={item.name} onChange={(event) => updateSublocation(index, { name: event.target.value })} placeholder="Bijvoorbeeld: Voorraadkast" />
                        </div>
                      ))}
                      <div><Button type="button" variant="secondary" onClick={addSublocation}>Sublocatie toevoegen</Button></div>
                    </>
                  )}
                </div>
              )}
              {questions.unpacking && checkbox('Uitpakken gebruiken', form.unpacking, (value) => setForm((current) => ({ ...current, unpacking: value })), 'capability-waar-unpacking')}
              {questions.receiptProcessing && checkbox('Kassabonverwerking gebruiken', form.receiptProcessing, (value) => setForm((current) => ({ ...current, receiptProcessing: value })), 'capability-waar-receipts')}
              {questions.almostOut && checkbox('Bijna op gebruiken', form.almostOut, (value) => setForm((current) => ({ ...current, almostOut: value })), 'capability-waar-almost-out')}
            </>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            <Button type="button" variant="secondary" onClick={() => setSelectedUseCase('')} disabled={isSaving}>Annuleren</Button>
            <Button type="button" onClick={submitExpansion} disabled={isSaving} data-testid="capability-expansion-submit">{isSaving ? 'Toevoegen…' : 'Toevoegen'}</Button>
          </div>
        </div>
      </Card>
    )
  }

  return (
    <AppShell title="Instellingen" showExit={false}>
      <div style={{ display: 'grid', gap: 18 }} data-testid="settings-capabilities-page">
        <Card>
          <div style={{ display: 'grid', gap: 16 }}>
            <div>
              <h2 style={{ margin: '0 0 8px 0', fontSize: 20 }}>Wat wil je met Inhuis doen?</h2>
              <p style={{ margin: 0, color: '#667085' }}>Je kunt Inhuis later uitbreiden. Wat al is ingesteld blijft behouden.</p>
            </div>
            {isLoading ? <div>Mogelijkheden laden…</div> : CAPABILITY_USE_CASES.map((item) => {
              const active = isUseCaseActive(state?.active_use_cases, item.key)
              return (
                <div key={item.key} style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', padding: 14, border: '1px solid #dfe4ea', borderRadius: 12 }} data-testid={`capability-card-${item.key}`}>
                  <div>
                    <div style={{ fontWeight: 700 }}>{item.title}</div>
                    <div style={{ color: '#667085', fontSize: 14 }}>{item.description}</div>
                  </div>
                  {active ? (
                    <span style={{ fontWeight: 700, color: '#0f5b32' }} data-testid={`capability-active-${item.key}`}>Actief</span>
                  ) : (
                    <Button type="button" variant="secondary" onClick={() => chooseUseCase(item.key)} data-testid={`capability-add-${item.key}`}>Toevoegen</Button>
                  )}
                </div>
              )
            })}
            {message ? <div className="rz-inline-feedback rz-inline-feedback--success" role="status">{message}</div> : null}
            {error ? <div className="rz-inline-feedback rz-inline-feedback--error" role="alert">{error}</div> : null}
          </div>
        </Card>
        {renderExpansionForm()}
      </div>
    </AppShell>
  )
}
