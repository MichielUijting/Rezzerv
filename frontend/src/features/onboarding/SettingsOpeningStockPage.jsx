import { useCallback, useEffect, useState } from 'react'
import AppShell from '../../app/AppShell.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import Input from '../../ui/Input.jsx'
import Table from '../../ui/Table.jsx'
import Pagination from '../../ui/Pagination.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'

const PAGE_SIZE = 10

const REVIEW_LABELS = {
  identity_review_required: 'Eerst artikelidentiteit controleren',
  unit_review_required: 'Eenheid niet als stuks te boeken',
  article_unavailable: 'Huishoudartikel niet meer beschikbaar',
  existing_stock: 'Er is al voorraad of voorraadhistorie',
}

const HISTORY_REASONS = {
  too_few_purchase_days: 'Te weinig afzonderlijke aankoopdagen',
  short_observation_period: 'Aankoopperiode te kort',
  irregular_observation_gap: 'Te grote tussenpozen tussen aankopen',
  stale_last_purchase: 'Laatste aankoop te lang geleden',
  incompatible_units: 'Eenheden zijn niet vergelijkbaar',
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: 'include',
    cache: 'no-store',
    headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}) },
    ...options,
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(typeof data?.detail === 'string' ? data.detail : 'Beginvoorraad kon niet worden verwerkt.')
  }
  return data
}

function quantityText(quantity, unit) {
  return quantity === null || quantity === undefined
    ? 'Onvoldoende gegevens'
    : new Intl.NumberFormat('nl-NL', { maximumFractionDigits: 3 }).format(quantity) + ' ' + (unit || '')
}

export default function SettingsOpeningStockPage() {
  const { showFeedback } = useAppFeedback()
  const [page, setPage] = useState(1)
  const [result, setResult] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async (targetPage = page) => {
    setLoading(true)
    try {
      const data = await requestJson('/api/onboarding/opening-stock?page=' + targetPage + '&page_size=' + PAGE_SIZE)
      setResult(data)
      setDrafts({})
    } catch (error) {
      setResult(null)
      showFeedback({ variant: 'error', message: error?.message || 'Beginvoorraad laden mislukt.' })
    } finally {
      setLoading(false)
    }
  }, [page, showFeedback])

  useEffect(() => { load(page) }, [page, load])

  function confirmRow(item) {
    if (busy || loading || !item?.can_confirm) return
    const raw = String(drafts[item.key] ?? '').trim()
    if (!/^(0|[1-9][0-9]*)$/.test(raw) || Number(raw) > 10000) {
      showFeedback({ variant: 'error', message: 'Vul zelf een heel aantal stuks tussen 0 en 10.000 in.' })
      return
    }
    const quantity = Number(raw)
    showFeedback({
      variant: 'warning',
      title: 'Beginvoorraad werkelijk vastleggen?',
      message: item.display_name + ': ' + quantity + (quantity === 1 ? ' stuk.' : ' stuks.'),
      detail: quantity === 0
        ? 'Je bevestigt dat de beginvoorraad nul is. Er wordt geen voorraad aangemaakt.'
        : 'Dit is jouw eigen telling of correctie. Na bevestigen ontstaat een echte voorraadpositie. Historische kassabonnen worden niet opnieuw verwerkt.',
      primaryActionLabel: 'Bevestigen',
      secondaryActionLabel: 'Annuleren',
      testId: 'opening-stock-confirm-dialog',
      onPrimaryAction: async () => {
        setBusy(true)
        try {
          const outcome = await requestJson('/api/onboarding/opening-stock/confirm', {
            method: 'POST',
            body: JSON.stringify({
              proposal_key: item.key,
              proposal_revision: item.proposal_revision,
              household_article_id: item.household_article_id,
              confirmed_quantity: quantity,
              explicitly_confirmed: true,
            }),
          })
          await load(page)
          showFeedback({
            variant: 'success',
            message: outcome.status === 'already_confirmed'
              ? 'Deze beginvoorraad was al bevestigd; niets dubbel geboekt.'
              : 'Beginvoorraad bevestigd en opgeslagen.',
          })
        } finally {
          setBusy(false)
        }
      },
    })
  }

  const total = Number(result?.total || 0)
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const items = result?.items || []

  return (
    <AppShell title="Beginvoorraad beoordelen" showExit={false}>
      <Card>
        <section data-testid="opening-stock-review" style={{ display: 'grid', gap: 16 }}>
          <div>
            <h2 style={{ marginTop: 0 }}>Beginvoorraad uit historische aankopen</h2>
            <p>
              Inhuis heeft eerdere aankopen geanalyseerd. Dit zijn <strong>schattingen</strong>,
              geen vastgestelde voorraad. Vul zelf de werkelijke beginvoorraad in en bevestig
              ieder artikel afzonderlijk. Zonder bevestiging verandert niets.
            </p>
            <p>De bestaande Voorraad en Bijna op worden niet aangepast door alleen dit scherm te openen.</p>
          </div>

          {loading ? <p role="status">Historische aankopen laden…</p> : null}
          {!loading && result?.status === 'legacy_not_enabled' ? (
            <p role="status">
              Voor dit huishouden is nog geen historische startdatum vastgelegd.
              Er is daarom geen voorstel voor beginvoorraad beschikbaar.
            </p>
          ) : null}
          {!loading && result?.status === 'source_limit_reached' ? (
            <p role="alert">De historie is te omvangrijk om veilig automatisch te beoordelen. Er is niets gewijzigd.</p>
          ) : null}

          {!loading && result?.status === 'analysis_only' && (
            <>
              <p>
                {total} artikelgroepen gevonden over maximaal {result.historical_window_days} dagen.
                Peildatum: <strong>{result.first_current_purchase_date}</strong>.
                {Number(result.excluded_rows || 0) > 0 ? (
                  <> {result.excluded_rows} onzekere of niet-fysieke bonregels zijn niet meegenomen.</>
                ) : null}
              </p>
              {!items.length ? <p>Geen historische artikelen op deze pagina.</p> : null}
              {items.length ? (
                <>
                  <Table dataTestId="opening-stock-table" tableClassName="rz-data-table--sticky-header">
                    <thead>
                      <tr className="rz-table-header">
                        <th scope="col">Artikel</th>
                        <th scope="col" style={{ textAlign: 'right' }}>Aankoopdagen</th>
                        <th scope="col" style={{ textAlign: 'right' }}>Koopinterval</th>
                        <th scope="col" style={{ textAlign: 'right' }}>Schatting</th>
                        <th scope="col">Beoordeling</th>
                        <th scope="col">Mijn beginvoorraad</th>
                        <th scope="col">Actie</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((item) => (
                        <tr key={item.key + ':' + item.unit}>
                          <td>
                            <strong>{item.display_name}</strong>
                            {item.estimate_status !== 'indicative_unconfirmed' ? (
                              <div>{HISTORY_REASONS[item.reason] || 'Onvoldoende bewijs voor een schatting'}</div>
                            ) : null}
                            <small>Laatste aankoop: {item.last_purchase_date}</small>
                          </td>
                          <td style={{ textAlign: 'right' }}>{item.purchase_day_count}</td>
                          <td style={{ textAlign: 'right' }}>
                            {item.average_purchase_interval_days != null
                              ? item.average_purchase_interval_days + ' dagen' : '—'}
                          </td>
                          <td style={{ textAlign: 'right' }}>{quantityText(item.estimated_opening_quantity, item.unit)}</td>
                          <td>
                            {item.review_status === 'confirmed'
                              ? 'Bevestigd: ' + item.confirmed_quantity + ' stuks'
                              : item.can_confirm
                                ? 'Klaar voor jouw telling'
                                : REVIEW_LABELS[item.review_status] || 'Controle nodig'}
                          </td>
                          <td>
                            {item.can_confirm ? (
                              <Input
                                type="number"
                                min="0"
                                max="10000"
                                step="1"
                                inputMode="numeric"
                                value={drafts[item.key] ?? ''}
                                onChange={(event) => setDrafts((old) => ({ ...old, [item.key]: event.target.value }))}
                                aria-label={'Werkelijke beginvoorraad voor ' + item.display_name + ' in stuks'}
                                placeholder="Eigen aantal"
                                disabled={busy}
                              />
                            ) : '—'}
                          </td>
                          <td>
                            <Button
                              type="button"
                              variant="secondary"
                              disabled={!item.can_confirm || busy}
                              onClick={() => confirmRow(item)}
                              data-testid="opening-stock-review-confirm"
                            >
                              Controleren
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                  <Pagination page={page} pageCount={pageCount}
                    onPageChange={(next) => { setDrafts({}); setPage(next) }}
                    disabled={busy || loading} />
                </>
              ) : null}
              <p>
                Producten zonder één bewezen huishoudartikel, onbewezen productkoppelingen,
                synoniemgroepen of hoeveelheden in kilogram/liter kunnen hier nog niet worden geboekt. Dit voorkomt
                verkeerde artikelkoppelingen en onbedoelde eenheidsconversies.
              </p>
            </>
          )}
        </section>
      </Card>
    </AppShell>
  )
}
