import { useEffect, useState } from 'react'
import AppShell from '../../app/AppShell.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import Input from '../../ui/Input.jsx'
import {
  createPlatformThread,
  downloadPlatformSupportCsv,
  getPlatformSupportScope,
  listPlatformThreads,
  readPlatformThread,
  replyPlatformThread,
  updatePlatformThreadStatus,
} from './supportApi.js'

const STATUSES = ['', 'Open', 'In behandeling', 'Gesloten']
const AUTO_REFRESH_MS = 2000

export default function PlatformSupportPage() {
  const [threads, setThreads] = useState([])
  const [selected, setSelected] = useState(null)
  const [status, setStatus] = useState('')
  const [householdId, setHouseholdId] = useState('')
  const [targetHouseholdId, setTargetHouseholdId] = useState('')
  const [supportScope, setSupportScope] = useState(null)
  const [subject, setSubject] = useState('')
  const [message, setMessage] = useState('')
  const [recipientType, setRecipientType] = useState('single_household_admin')
  const [adminIds, setAdminIds] = useState('')
  const [replyAllowed, setReplyAllowed] = useState(true)
  const [reply, setReply] = useState('')
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [lastRefreshedAt, setLastRefreshedAt] = useState(null)
  const [refreshCount, setRefreshCount] = useState(0)

  const unrestricted = supportScope?.onbeperkt === true
  const allowedHouseholds = supportScope?.toegestane_huishoudens || []

  async function loadScope() {
    try {
      const data = await getPlatformSupportScope()
      setSupportScope(data)
      if (!data?.onbeperkt) {
        const allowed = data?.toegestane_huishoudens || []
        setTargetHouseholdId((current) => allowed.includes(current) ? current : (allowed[0] || ''))
        setHouseholdId((current) => current && !allowed.includes(current) ? '' : current)
      }
    } catch (error) {
      setFeedback(error.message)
    }
  }

  async function loadThreads({ showBusy = false, showErrors = true } = {}) {
    if (showBusy) setBusy(true)
    try {
      const data = await listPlatformThreads({ status, householdId })
      setThreads(data?.items || [])
      if (selected?.thread?.id) setSelected(await readPlatformThread(selected.thread.id))
      setLastRefreshedAt(new Date())
      setRefreshCount((value) => value + 1)
    } catch (error) {
      if (showErrors) setFeedback(error.message)
    } finally {
      if (showBusy) setBusy(false)
    }
  }

  useEffect(() => {
    loadScope()
  }, [])

  useEffect(() => {
    loadThreads({ showBusy: true })
  }, [status])

  useEffect(() => {
    let cancelled = false
    let timer = null
    let running = false

    const schedule = () => {
      if (!cancelled) timer = window.setTimeout(run, AUTO_REFRESH_MS)
    }

    const run = async () => {
      if (cancelled || running) return
      running = true
      await loadThreads({ showBusy: false, showErrors: false })
      running = false
      schedule()
    }

    const refreshImmediately = () => {
      if (document.visibilityState === 'visible') run()
    }

    schedule()
    window.addEventListener('focus', refreshImmediately)
    document.addEventListener('visibilitychange', refreshImmediately)

    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
      window.removeEventListener('focus', refreshImmediately)
      document.removeEventListener('visibilitychange', refreshImmediately)
    }
  }, [status, householdId, selected?.thread?.id])

  async function openThread(id) {
    setBusy(true)
    setFeedback('')
    try { setSelected(await readPlatformThread(id)) }
    catch (error) { setFeedback(error.message) }
    finally { setBusy(false) }
  }

  async function submitNew(event) {
    event.preventDefault()
    setBusy(true)
    setFeedback('')
    try {
      const admin_user_ids = adminIds.split(',').map((value) => value.trim()).filter(Boolean)
      const created = await createPlatformThread({
        subject,
        message,
        household_id: targetHouseholdId,
        recipient_type: recipientType,
        admin_user_ids,
        reply_allowed: replyAllowed,
      })
      setSubject('')
      setMessage('')
      setAdminIds('')
      await loadThreads()
      await openThread(created.thread_id)
      setFeedback('Melding verzonden.')
    } catch (error) {
      setFeedback(error.message)
    } finally {
      setBusy(false)
    }
  }

  async function submitReply(event) {
    event.preventDefault()
    if (!selected?.thread?.id) return
    setBusy(true)
    setFeedback('')
    try {
      await replyPlatformThread(selected.thread.id, reply)
      setReply('')
      setSelected(await readPlatformThread(selected.thread.id))
      await loadThreads()
      setFeedback('Reactie verzonden.')
    } catch (error) {
      setFeedback(error.message)
    } finally {
      setBusy(false)
    }
  }

  async function changeStatus(nextStatus) {
    if (!selected?.thread?.id) return
    setBusy(true)
    setFeedback('')
    try {
      await updatePlatformThreadStatus(selected.thread.id, nextStatus)
      setSelected(await readPlatformThread(selected.thread.id))
      await loadThreads()
      setFeedback('Status bijgewerkt.')
    } catch (error) {
      setFeedback(error.message)
    } finally {
      setBusy(false)
    }
  }

  const refreshLabel = lastRefreshedAt
    ? `Laatst ververst: ${lastRefreshedAt.toLocaleTimeString('nl-NL')} · cyclus ${refreshCount}`
    : 'Nog niet ververst'

  return (
    <AppShell title="Superuser / Meldingen" showExit={false}>
      <div className="rz-support-layout" data-testid="platform-support-page">
        <Card>
          <div className="rz-support-toolbar">
            <div>
              <h2>Alle meldingen</h2>
              <p>Automatische verversing iedere 2 seconden.</p>
              {supportScope ? <p>Rol: {supportScope.rol} · {unrestricted ? 'alle huishoudens' : `huishouden 0 en eigen huishoudens (${allowedHouseholds.join(', ')})`}</p> : null}
              <p aria-live="polite" data-testid="platform-support-refresh-status">{refreshLabel}</p>
            </div>
            <Button variant="secondary" onClick={() => downloadPlatformSupportCsv(status).catch((error) => setFeedback(error.message))}>CSV exporteren</Button>
          </div>
          <div className="rz-support-filters">
            <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter op status">
              {STATUSES.map((value) => <option key={value || 'all'} value={value}>{value || 'Alle statussen'}</option>)}
            </select>
            {unrestricted ? (
              <Input value={householdId} onChange={(event) => setHouseholdId(event.target.value)} placeholder="Huishoud-ID" />
            ) : (
              <select value={householdId} onChange={(event) => setHouseholdId(event.target.value)} aria-label="Filter op toegestaan huishouden">
                <option value="">Alle toegestane huishoudens</option>
                {allowedHouseholds.map((value) => <option key={value} value={value}>Huishouden {value}</option>)}
              </select>
            )}
            <Button variant="secondary" onClick={() => loadThreads({ showBusy: true })}>Zoeken</Button>
          </div>
          {!busy && !threads.length ? <p>Geen meldingen gevonden.</p> : null}
          <div className="rz-support-list">
            {threads.map((thread) => (
              <button key={thread.id} type="button" className="rz-support-thread" onClick={() => openThread(thread.id)}>
                <strong>{thread.subject}</strong>
                <span>{thread.thread_number} · {thread.status}</span>
                <span>Huishouden {thread.household_id || '-'} · {thread.message_count} bericht(en)</span>
              </button>
            ))}
          </div>
        </Card>

        <Card>
          {selected ? (
            <>
              <div className="rz-support-detail-head">
                <div><h2>{selected.thread.subject}</h2><p>{selected.thread.thread_number} · huishouden {selected.thread.household_id} · {selected.thread.status}</p></div>
                <Button variant="secondary" onClick={() => setSelected(null)}>Nieuwe melding</Button>
              </div>
              <div className="rz-support-status-actions" aria-label="Status van melding">
                {STATUSES.filter(Boolean).map((value) => (
                  <Button key={value} variant={selected.thread.status === value ? 'primary' : 'secondary'} onClick={() => changeStatus(value)} disabled={busy}>{value}</Button>
                ))}
              </div>
              <div className="rz-support-conversation">
                {(selected.messages || []).map((item) => (
                  <article key={item.id} className="rz-support-message">
                    <strong>{item.sender_name}</strong><small>{item.sender_role} · {item.created_at}</small><p>{item.message_text}</p>
                  </article>
                ))}
              </div>
              <form onSubmit={submitReply} className="rz-support-form">
                <label>Reactie<textarea value={reply} onChange={(event) => setReply(event.target.value)} required maxLength={10000} /></label>
                <Button variant="primary" type="submit" disabled={busy || !reply.trim()}>Versturen</Button>
              </form>
            </>
          ) : (
            <form onSubmit={submitNew} className="rz-support-form">
              <h2>Nieuwe melding aan huishoudadmin(s)</h2>
              <label>Huishouden
                {unrestricted ? (
                  <Input value={targetHouseholdId} onChange={(event) => setTargetHouseholdId(event.target.value)} required />
                ) : (
                  <select value={targetHouseholdId} onChange={(event) => setTargetHouseholdId(event.target.value)} required>
                    {allowedHouseholds.map((value) => <option key={value} value={value}>Huishouden {value}</option>)}
                  </select>
                )}
              </label>
              <label>Ontvangers<select value={recipientType} onChange={(event) => setRecipientType(event.target.value)}><option value="single_household_admin">Eén huishoudadmin</option><option value="all_household_admins">Alle huishoudadmins</option></select></label>
              <label>Admin-gebruikers-ID's<Input value={adminIds} onChange={(event) => setAdminIds(event.target.value)} placeholder="Komma-gescheiden" required /></label>
              <label>Onderwerp<Input value={subject} onChange={(event) => setSubject(event.target.value)} required maxLength={250} /></label>
              <label>Bericht<textarea value={message} onChange={(event) => setMessage(event.target.value)} required maxLength={10000} /></label>
              <label className="rz-support-checkbox"><input type="checkbox" checked={replyAllowed} onChange={(event) => setReplyAllowed(event.target.checked)} /> Antwoorden toestaan</label>
              <Button variant="primary" type="submit" disabled={busy || !targetHouseholdId}>Melding versturen</Button>
            </form>
          )}
          {feedback ? <p className="rz-support-feedback" role="status">{feedback}</p> : null}
        </Card>
      </div>
    </AppShell>
  )
}
