import { useEffect, useState } from 'react'
import Button from '../../ui/Button.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import {
  fetchAlmostOutSettings,
  saveAlmostOutSettings,
  isValidPredictionDays,
} from '../settings/services/almostOutSettingsService.js'

// Both Bijna op views edit the same household key as Instellingen.
// Never overwrite unrelated fields with stale values from the page.
export default function AlmostOutPredictionTerm({ onSaved }) {
  const { showFeedback } = useAppFeedback()
  const [settings, setSettings] = useState(null)
  const [value, setValue] = useState('')
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let active = true
    fetchAlmostOutSettings()
      .then((next) => {
        if (!active) return
        setSettings(next)
        setValue(String(next.predictionDays))
      })
      .catch((error) => {
        if (active) showFeedback({
          variant: 'error',
          message: error?.message || 'Voorspeltermijn kon niet worden geladen.',
        })
      })
    return () => { active = false }
  }, [showFeedback])

  function cancel() {
    setValue(String(settings.predictionDays))
    setEditing(false)
  }

  async function save() {
    const days = Number(value)
    if (!isValidPredictionDays(value)) {
      showFeedback({ variant: 'error', message: 'Voorspeltermijn moet een heel niet-negatief aantal dagen zijn.' })
      return
    }
    if (!settings?.isHouseholdAdmin || busy) return
    setBusy(true)
    try {
      // Refresh immediately before the write so unrelated prediction/shopping
      // settings are preserved. Detect a concurrent edit to this same value.
      const latest = await fetchAlmostOutSettings()
      if (!latest.isHouseholdAdmin) throw new Error('Alleen de huishoudbeheerder kan de voorspeltermijn wijzigen.')
      if (latest.predictionDays !== settings.predictionDays) {
        setSettings(latest)
        setValue(String(latest.predictionDays))
        setEditing(false)
        throw new Error('De voorspeltermijn is inmiddels aangepast. De nieuwste waarde is geladen.')
      }
      const saved = await saveAlmostOutSettings({ ...latest, predictionDays: days })
      setSettings(saved)
      setValue(String(saved.predictionDays))
      setEditing(false)
      showFeedback({ variant: 'success', message: `Voorspeltermijn opgeslagen: ${saved.predictionDays} dagen.` })
      await onSaved?.()
    } catch (error) {
      showFeedback({ variant: 'error', message: error?.message || 'Voorspeltermijn kon niet worden opgeslagen.' })
    } finally {
      setBusy(false)
    }
  }

  return <section data-testid="almost-out-prediction-term"
    aria-label="Voorspeltermijn" style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: '8px 0' }}>
    <span data-testid="almost-out-prediction-current">
      <strong>Voorspeltermijn:</strong>{' '}
      {settings ? `${settings.predictionDays} dagen` : 'Laden…'}
      {settings && !settings.predictionEnabled ? ' (voorspelling uitgeschakeld)' : ''}
    </span>
    {settings?.isHouseholdAdmin && !editing ? (
      <Button type="button" variant="secondary" disabled={busy} onClick={() => setEditing(true)}
        data-testid="almost-out-prediction-edit">Wijzigen</Button>
    ) : null}
    {editing ? <>
      <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span>Voorspeltermijn (dagen)</span>
        <input className="rz-input" type="number" inputMode="numeric" min="0" step="1"
          value={value} onChange={(event) => setValue(event.target.value)}
          disabled={busy} data-testid="almost-out-prediction-input"
          style={{ width: 88 }} />
      </label>
      <Button type="button" disabled={busy} onClick={save}
        data-testid="almost-out-prediction-save">Opslaan</Button>
      <Button type="button" variant="secondary" disabled={busy} onClick={cancel}>Annuleren</Button>
    </> : null}
  </section>
}
