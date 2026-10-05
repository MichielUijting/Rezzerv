import { useEffect, useState } from 'react'
import AppShell from '../../app/AppShell.jsx'
import Button from '../../ui/Button.jsx'
import Card from '../../ui/Card.jsx'
import Input from '../../ui/Input.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import {
  createHouseholdResident,
  deleteHouseholdResident,
  fetchHouseholdProfile,
  saveHouseholdProfile,
  updateHouseholdResident,
} from './services/householdProfileService.js'

const EMPTY_RESIDENT = {
  id: '',
  first_name: '',
  last_name: '',
  resident_type: 'adult',
  birth_date: '',
  age_band: '',
  linked_user_id: '',
}

const AGE_BANDS = [
  ['', 'Niet ingevuld'],
  ['0_3', '0–3 jaar'],
  ['4_12', '4–12 jaar'],
  ['13_17', '13–17 jaar'],
  ['18_34', '18–34 jaar'],
  ['35_49', '35–49 jaar'],
  ['50_64', '50–64 jaar'],
  ['65_79', '65–79 jaar'],
  ['80_plus', '80 jaar en ouder'],
]

function profileForm(payload = {}) {
  return {
    household_name: payload.household_name || '',
    street: payload.street || '',
    house_number: payload.house_number || '',
    house_number_addition: payload.house_number_addition || '',
    postal_code: payload.postal_code || '',
    city: payload.city || '',
    country_code: payload.country_code || 'NL',
    preferred_stores: Array.isArray(payload.preferred_stores) ? payload.preferred_stores.join(', ') : '',
    shopping_interval_days: payload.shopping_interval_days ?? '',
    default_reserve_days: payload.default_reserve_days ?? '',
  }
}

function residentForm(resident = EMPTY_RESIDENT) {
  return {
    id: resident.id || '',
    first_name: resident.first_name || '',
    last_name: resident.last_name || '',
    resident_type: resident.resident_type || 'adult',
    birth_date: resident.birth_date || '',
    age_band: resident.age_band || '',
    linked_user_id: resident.linked_user_id || '',
  }
}

export default function SettingsHouseholdProfilePage() {
  const { showFeedback } = useAppFeedback()
  const [data, setData] = useState(null)
  const [form, setForm] = useState(profileForm())
  const [resident, setResident] = useState(residentForm())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [residentToRemove, setResidentToRemove] = useState(null)

  async function load() {
    setLoading(true)
    try {
      const payload = await fetchHouseholdProfile()
      setData(payload)
      setForm(profileForm(payload))
    } catch (error) {
      showFeedback({ variant: 'error', title: 'Huishoudprofiel niet geladen', message: error?.message || 'De gegevens konden niet worden geladen.' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  function setField(key, value) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  async function saveProfile(event) {
    event.preventDefault()
    if (!data?.can_manage || saving) return
    setSaving(true)
    try {
      const payload = await saveHouseholdProfile({
        ...form,
        preferred_stores: String(form.preferred_stores || '').split(',').map((item) => item.trim()).filter(Boolean),
        shopping_interval_days: form.shopping_interval_days === '' ? null : Number(form.shopping_interval_days),
        default_reserve_days: form.default_reserve_days === '' ? null : Number(form.default_reserve_days),
      })
      setData(payload)
      setForm(profileForm(payload))
      showFeedback({ variant: 'success', message: 'Huishoudprofiel opgeslagen.' })
    } catch (error) {
      showFeedback({ variant: 'error', title: 'Huishoudprofiel niet opgeslagen', message: error?.message || 'De wijziging kon niet worden opgeslagen.' })
    } finally {
      setSaving(false)
    }
  }

  async function saveResident(event) {
    event.preventDefault()
    if (!data?.can_manage || saving) return
    setSaving(true)
    const payload = {
      first_name: resident.first_name,
      last_name: resident.last_name || null,
      resident_type: resident.resident_type,
      birth_date: resident.birth_date || null,
      age_band: resident.age_band || null,
      linked_user_id: resident.linked_user_id || null,
    }
    try {
      const next = resident.id
        ? await updateHouseholdResident(resident.id, payload)
        : await createHouseholdResident(payload)
      setData(next)
      setForm(profileForm(next))
      setResident(residentForm())
      showFeedback({ variant: 'success', message: resident.id ? 'Bewoner bijgewerkt.' : 'Bewoner toegevoegd.' })
    } catch (error) {
      showFeedback({ variant: 'error', title: 'Bewoner niet opgeslagen', message: error?.message || 'De bewoner kon niet worden opgeslagen.' })
    } finally {
      setSaving(false)
    }
  }

  async function confirmRemoveResident() {
    if (!data?.can_manage || saving || !residentToRemove) return
    const item = residentToRemove
    setSaving(true)
    try {
      const next = await deleteHouseholdResident(item.id)
      setData(next)
      setForm(profileForm(next))
      if (resident.id === item.id) setResident(residentForm())
      setResidentToRemove(null)
      showFeedback({ variant: 'success', message: 'Bewoner verwijderd.' })
    } catch (error) {
      showFeedback({ variant: 'error', title: 'Bewoner niet verwijderd', message: error?.message || 'De bewoner kon niet worden verwijderd.' })
    } finally {
      setSaving(false)
    }
  }

  const canManage = Boolean(data?.can_manage)

  return (
    <AppShell title="Instellingen" showExit={false}>
      <div className="rz-content"><div className="rz-content-inner" data-testid="settings-household-profile-page">
        <Card>
          <h2>Huishoudprofiel</h2>
          <p>Deze gedeelde gegevens helpen Inhuis om voorraad, boodschappen en toekomstige prognoses beter op het huishouden af te stemmen.</p>
          {loading ? <p role="status">Huishoudprofiel laden…</p> : (
            <form onSubmit={saveProfile} style={{ display: 'grid', gap: 16 }}>
              <Input label="Naam huishouden" value={form.household_name} onChange={(e) => setField('household_name', e.target.value)} disabled={!canManage || saving} required />
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12 }}>
                <Input label="Straat" value={form.street} onChange={(e) => setField('street', e.target.value)} disabled={!canManage || saving} />
                <Input label="Huisnummer" value={form.house_number} onChange={(e) => setField('house_number', e.target.value)} disabled={!canManage || saving} />
                <Input label="Toevoeging" value={form.house_number_addition} onChange={(e) => setField('house_number_addition', e.target.value)} disabled={!canManage || saving} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12 }}>
                <Input label="Postcode" value={form.postal_code} onChange={(e) => setField('postal_code', e.target.value)} disabled={!canManage || saving} />
                <Input label="Woonplaats" value={form.city} onChange={(e) => setField('city', e.target.value)} disabled={!canManage || saving} />
                <Input label="Landcode" value={form.country_code} maxLength={2} onChange={(e) => setField('country_code', e.target.value.toUpperCase())} disabled={!canManage || saving} />
              </div>
              <Input label="Voorkeurswinkels (gescheiden door komma's)" value={form.preferred_stores} onChange={(e) => setField('preferred_stores', e.target.value)} disabled={!canManage || saving} />
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
                <Input label="Normaal aantal dagen tussen boodschappen" type="number" min="1" max="90" value={form.shopping_interval_days} onChange={(e) => setField('shopping_interval_days', e.target.value)} disabled={!canManage || saving} />
                <Input label="Standaard reservevoorraad in dagen" type="number" min="0" max="90" value={form.default_reserve_days} onChange={(e) => setField('default_reserve_days', e.target.value)} disabled={!canManage || saving} />
              </div>
              {canManage ? <div><Button type="submit" disabled={saving}>{saving ? 'Opslaan…' : 'Huishoudprofiel opslaan'}</Button></div> : <p>Alleen een Beheerder kan het gedeelde huishoudprofiel wijzigen.</p>}
            </form>
          )}
        </Card>

        {!loading ? (
          <Card>
            <h2>Bewoners — {data?.resident_count ?? 0}</h2>
            <p>Bewoners staan los van Inhuis-accounts. Daardoor kan Inhuis de feitelijke huishoudsamenstelling gebruiken zonder voor iedere bewoner een account te vereisen.</p>
            <div style={{ display: 'grid', gap: 10, marginBottom: 18 }}>
              {(data?.residents || []).map((item) => (
                <div key={item.id} data-testid={`household-resident-${item.id}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                  <div>
                    <strong>{item.first_name}{item.last_name ? ` ${item.last_name}` : ''}</strong>
                    <div>{item.resident_type === 'adult' ? 'Volwassene' : item.resident_type === 'child' ? 'Kind' : 'Anders'}{item.birth_date ? ` · geboren ${item.birth_date}` : item.age_band ? ` · ${AGE_BANDS.find(([key]) => key === item.age_band)?.[1] || item.age_band}` : ''}</div>
                  </div>
                  {canManage ? <div style={{ display: 'flex', gap: 8 }}>
                    <Button type="button" variant="secondary" onClick={() => setResident(residentForm(item))}>Wijzigen</Button>
                    <Button type="button" variant="secondary" onClick={() => setResidentToRemove(item)}>Verwijderen</Button>
                  </div> : null}
                </div>
              ))}
              {(data?.residents || []).length === 0 ? <p>Er zijn nog geen bewoners vastgelegd.</p> : null}
            </div>

            {canManage ? (
              <form onSubmit={saveResident} style={{ display: 'grid', gap: 12 }} data-testid="household-resident-form">
                <h3>{resident.id ? 'Bewoner wijzigen' : 'Bewoner toevoegen'}</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
                  <Input label="Voornaam" value={resident.first_name} onChange={(e) => setResident((current) => ({ ...current, first_name: e.target.value }))} required disabled={saving} />
                  <Input label="Achternaam (optioneel)" value={resident.last_name} onChange={(e) => setResident((current) => ({ ...current, last_name: e.target.value }))} disabled={saving} />
                </div>
                <label className="rz-input-field">
                  <span className="rz-label">Bewonerstype</span>
                  <select className="rz-input" value={resident.resident_type} onChange={(e) => setResident((current) => ({ ...current, resident_type: e.target.value }))} disabled={saving}>
                    <option value="adult">Volwassene</option>
                    <option value="child">Kind</option>
                    <option value="other">Anders</option>
                  </select>
                </label>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
                  <Input label="Geboortedatum (optioneel)" type="date" value={resident.birth_date} onChange={(e) => setResident((current) => ({ ...current, birth_date: e.target.value, age_band: e.target.value ? '' : current.age_band }))} disabled={saving} />
                  <label className="rz-input-field">
                    <span className="rz-label">Leeftijdscategorie (optioneel)</span>
                    <select className="rz-input" value={resident.age_band} onChange={(e) => setResident((current) => ({ ...current, age_band: e.target.value, birth_date: e.target.value ? '' : current.birth_date }))} disabled={saving}>
                      {AGE_BANDS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                    </select>
                  </label>
                </div>
                <label className="rz-input-field">
                  <span className="rz-label">Gekoppeld Inhuis-account (optioneel)</span>
                  <select className="rz-input" value={resident.linked_user_id} onChange={(e) => setResident((current) => ({ ...current, linked_user_id: e.target.value }))} disabled={saving}>
                    <option value="">Geen account gekoppeld</option>
                    {(data?.linked_users || []).map((user) => <option key={user.user_id} value={user.user_id}>{user.display_name || user.email}</option>)}
                  </select>
                </label>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Button type="submit" disabled={saving}>{saving ? 'Opslaan…' : resident.id ? 'Bewoner opslaan' : 'Bewoner toevoegen'}</Button>
                  {resident.id ? <Button type="button" variant="secondary" onClick={() => setResident(residentForm())} disabled={saving}>Annuleren</Button> : null}
                </div>
              </form>
            ) : null}
          </Card>
        ) : null}
      </div></div>
      {residentToRemove ? (
        <div className="rz-modal-backdrop" role="presentation">
          <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="resident-remove-title" data-testid="household-resident-remove-modal">
            <h3 id="resident-remove-title" className="rz-modal-title">Bewoner verwijderen</h3>
            <p className="rz-modal-text">Weet je zeker dat je <strong>{residentToRemove.first_name}</strong> uit de bewonerslijst wilt verwijderen?</p>
            <div className="rz-modal-actions">
              <Button type="button" variant="secondary" disabled={saving} onClick={() => setResidentToRemove(null)}>Annuleren</Button>
              <Button type="button" disabled={saving} onClick={confirmRemoveResident}>{saving ? 'Bezig…' : 'Verwijderen'}</Button>
            </div>
          </div>
        </div>
      ) : null}
    </AppShell>
  )
}
