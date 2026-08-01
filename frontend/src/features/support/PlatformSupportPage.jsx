import { useEffect, useState } from 'react'
import AppShell from '../../app/AppShell.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import Input from '../../ui/Input.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { readStoredAuthContext } from '../../lib/authSession.js'
import { getRezzervVersionTag } from '../../ui/version.js'
import {
  createPlatformBroadcast,
  deletePlatformThread,
  downloadPlatformSupportCsv,
  listPlatformThreads,
  readPlatformThread,
  replyPlatformThread,
  updatePlatformThreadStatus,
} from './supportApi.js'

const STATUSES = ['Open', '', 'In behandeling', 'Gesloten']
const AUTO_REFRESH_MS = 2000

export default function PlatformSupportPage() {
  const { showFeedback } = useAppFeedback()
  const currentUserId = String(readStoredAuthContext()?.user_id || readStoredAuthContext()?.email || '').trim().toLowerCase()
  const [threads, setThreads] = useState([])
  const [selected, setSelected] = useState(null)
  const [status, setStatus] = useState('Open')
  const [householdId, setHouseholdId] = useState('')
  const [reply, setReply] = useState('')
  const [broadcastSubject, setBroadcastSubject] = useState('')
  const [broadcastMessage, setBroadcastMessage] = useState('')
  const [broadcastReplyAllowed, setBroadcastReplyAllowed] = useState(true)
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [lastRefreshedAt, setLastRefreshedAt] = useState(null)
  const [refreshCount, setRefreshCount] = useState(0)
  const [readThreadIds, setReadThreadIds] = useState(() => new Set())

  function isUnread(thread) {
    return Boolean(thread?.last_sender_user_id)
      && String(thread.last_sender_user_id).trim().toLowerCase() !== currentUserId
      && !readThreadIds.has(thread.id)
  }

  async function loadThreads({ showBusy = false, showErrors = true } = {}) {
    if (showBusy) setBusy(true)
    if (showErrors) setFeedback('')
    try {
      const data = await listPlatformThreads({ status, householdId })
      const items = data?.items || []
      setThreads(items)
      if (selected?.thread?.id) {
        const stillVisible = items.some((thread) => thread.id === selected.thread.id)
        setSelected(stillVisible ? await readPlatformThread(selected.thread.id) : null)
      }
      setLastRefreshedAt(new Date())
      setRefreshCount((value) => value + 1)
    } catch (error) {
      if (showErrors) setFeedback(error.message)
    } finally {
      if (showBusy) setBusy(false)
    }
  }

  useEffect(() => { loadThreads({ showBusy: true }) }, [status])

  useEffect(() => {
    let cancelled = false
    let timer = null
    const poll = async () => {
      await loadThreads({ showBusy: false, showErrors: false })
      if (!cancelled) timer = window.setTimeout(poll, AUTO_REFRESH_MS)
    }
    timer = window.setTimeout(poll, AUTO_REFRESH_MS)
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [status, householdId, selected?.thread?.id])

  async function openThread(id) {
    setBusy(true)
    setFeedback('')
    try {
      setSelected(await readPlatformThread(id))
      setReadThreadIds((current) => new Set([...current, id]))
    } catch (error) { setFeedback(error.message) }
    finally { setBusy(false) }
  }

  async function performRemoveThread(threadId) {
    setBusy(true)
    setFeedback('')
    try {
      await deletePlatformThread(threadId)
      if (selected?.thread?.id === threadId) setSelected(null)
      await loadThreads()
      setFeedback('Melding verwijderd.')
    } finally {
      setBusy(false)
    }
  }

  function removeThread(threadId, threadSubject) {
    showFeedback({
      variant: 'warning',
      title: 'Melding verwijderen',
      message: `Wil je de melding “${threadSubject}” definitief verwijderen?`,
      detail: 'Deze actie kan niet ongedaan worden gemaakt.',
      dismissMode: 'action-only',
      primaryActionLabel: 'Verwijderen',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: async () => performRemoveThread(threadId),
      key: `platform-support-delete-${threadId}`,
      testId: 'support-delete-confirmation',
    })
  }

  async function performBroadcast() {
    setBusy(true)
    setFeedback('')
    try {
      const result = await createPlatformBroadcast({
        subject: broadcastSubject,
        message: broadcastMessage,
        reply_allowed: broadcastReplyAllowed,
        app_version: getRezzervVersionTag(),
      })
      setBroadcastSubject('')
      setBroadcastMessage('')
      await loadThreads()
      setFeedback(`Melding verzonden aan ${result.recipient_count} actieve leden.`)
    } finally {
      setBusy(false)
    }
  }

  function confirmBroadcast(event) {
    event.preventDefault()
    showFeedback({
      variant: 'warning',
      title: 'Melding aan alle leden versturen',
      message: `Wil je “${broadcastSubject}” naar alle actieve Rezzerv-leden sturen?`,
      detail: 'Voor iedere actieve gebruiker wordt een eigen gesprek aangemaakt.',
      dismissMode: 'action-only',
      primaryActionLabel: 'Versturen',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: performBroadcast,
      key: 'platform-support-broadcast-confirmation',
      testId: 'support-broadcast-confirmation',
    })
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
      setFeedback('Reactie verzonden aan de indiener.')
    } catch (error) { setFeedback(error.message) }
    finally { setBusy(false) }
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
    } catch (error) { setFeedback(error.message) }
    finally { setBusy(false) }
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
              <p>Hier staan meldingen van alle huishoudens, inclusief nieuwe inzendingen.</p>
              <p aria-live="polite" className="rz-support-refresh">{refreshLabel}</p>
            </div>
            <Button variant="secondary" onClick={() => downloadPlatformSupportCsv(status).catch((error) => setFeedback(error.message))}>CSV exporteren</Button>
          </div>
          <div className="rz-support-filters">
            <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter op status">
              {STATUSES.map((value) => <option key={value || 'all'} value={value}>{value || 'Alle statussen'}</option>)}
            </select>
            <Input value={householdId} onChange={(event) => setHouseholdId(event.target.value)} placeholder="Huishoud-ID" />
            <Button variant="secondary" onClick={() => loadThreads({ showBusy: true })}>Zoeken</Button>
          </div>
          {busy && !threads.length ? <p>Bezig met laden…</p> : null}
          {!busy && !threads.length ? <p>Geen meldingen gevonden.</p> : null}
          <div className="rz-support-list">
            {threads.map((thread) => (
              <div key={thread.id} className={`rz-support-thread-row ${isUnread(thread) ? 'rz-support-thread-row--unread' : ''}`}>
                <button type="button" className="rz-support-thread" onClick={() => openThread(thread.id)}>
                  <strong>{thread.subject}</strong>
                  <span>{thread.thread_number} · {thread.status}</span>
                  <span>Huishouden {thread.household_id || '-'} · {thread.created_by_name} · {thread.message_count} bericht(en)</span>
                </button>
                <button type="button" className="rz-support-delete" aria-label={`Melding ${thread.subject} verwijderen`} onClick={() => removeThread(thread.id, thread.subject)}>🗑</button>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          {selected ? (
            <>
              <div className="rz-support-detail-head">
                <div>
                  <h2>{selected.thread.subject}</h2>
                  <p>{selected.thread.thread_number} · huishouden {selected.thread.household_id} · {selected.thread.status}</p>
                </div>
                <Button variant="secondary" onClick={() => setSelected(null)}>Nieuwe melding aan alle leden</Button>
              </div>
              <div className="rz-support-status-actions" aria-label="Status van melding">
                {STATUSES.filter(Boolean).map((value) => (
                  <Button key={value} variant={selected.thread.status === value ? 'primary' : 'secondary'} onClick={() => changeStatus(value)} disabled={busy}>{value}</Button>
                ))}
              </div>
              <div className="rz-support-conversation">
                {(selected.messages || []).map((item) => (
                  <article key={item.id} className="rz-support-message">
                    <strong>{item.sender_name}</strong>
                    <small>{item.sender_role} · {item.created_at}</small>
                    <p>{item.message_text}</p>
                  </article>
                ))}
              </div>
              <form onSubmit={submitReply} className="rz-support-form">
                <label>Reactie<textarea value={reply} onChange={(event) => setReply(event.target.value)} required maxLength={10000} /></label>
                <Button variant="primary" type="submit" disabled={busy || !reply.trim()}>Versturen</Button>
              </form>
            </>
          ) : (
            <form onSubmit={confirmBroadcast} className="rz-support-form" data-testid="platform-support-broadcast-form">
              <h2>Nieuwe melding aan alle leden</h2>
              <p>Alleen de superuser kan een platformmelding naar alle actieve Rezzerv-leden sturen.</p>
              <label>Onderwerp<Input value={broadcastSubject} onChange={(event) => setBroadcastSubject(event.target.value)} required maxLength={250} /></label>
              <label>Bericht<textarea value={broadcastMessage} onChange={(event) => setBroadcastMessage(event.target.value)} required maxLength={10000} /></label>
              <label className="rz-support-checkbox"><input type="checkbox" checked={broadcastReplyAllowed} onChange={(event) => setBroadcastReplyAllowed(event.target.checked)} /> Antwoorden toestaan</label>
              <Button variant="primary" type="submit" disabled={busy || !broadcastSubject.trim() || !broadcastMessage.trim()}>Naar alle leden versturen</Button>
            </form>
          )}
          {feedback ? <p className="rz-support-feedback" role="status">{feedback}</p> : null}
        </Card>
      </div>
    </AppShell>
  )
}
