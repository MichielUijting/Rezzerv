import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import AppShell from '../../app/AppShell.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import Input from '../../ui/Input.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { readStoredAuthContext } from '../../lib/authSession.js'
import { getRezzervVersionTag } from '../../ui/version.js'
import {
  createHouseholdThread,
  deleteHouseholdThread,
  listHouseholdThreads,
  readHouseholdThread,
  replyHouseholdThread,
} from './supportApi.js'
import './support.css'

const STATUSES = ['Open', '', 'In behandeling', 'Gesloten']
const AUTO_REFRESH_MS = 3000

export default function HouseholdSupportPage() {
  const location = useLocation()
  const { showFeedback } = useAppFeedback()
  const query = useMemo(() => new URLSearchParams(location.search), [location.search])
  const originRoute = query.get('from') || '/meldingen'
  const originScreen = query.get('screen') || 'Rezzerv'
  const currentUserId = String(readStoredAuthContext()?.user_id || readStoredAuthContext()?.email || '').trim().toLowerCase()

  const [threads, setThreads] = useState([])
  const [selected, setSelected] = useState(null)
  const [status, setStatus] = useState('Open')
  const [subject, setSubject] = useState('')
  const [message, setMessage] = useState('')
  const [reply, setReply] = useState('')
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

  async function refresh({ showBusy = false, showErrors = true } = {}) {
    if (showBusy) setBusy(true)
    if (showErrors) setFeedback('')
    try {
      const data = await listHouseholdThreads(status)
      const ownThreads = data?.items || []
      setThreads(ownThreads)
      if (selected?.thread?.id && ownThreads.some((thread) => thread.id === selected.thread.id)) {
        setSelected(await readHouseholdThread(selected.thread.id))
      }
      setLastRefreshedAt(new Date())
      setRefreshCount((value) => value + 1)
    } catch (error) {
      if (showErrors) setFeedback(error.message)
    } finally {
      if (showBusy) setBusy(false)
    }
  }

  useEffect(() => { refresh({ showBusy: true }) }, [status])

  useEffect(() => {
    let cancelled = false
    const timer = window.setInterval(() => {
      if (!cancelled) refresh({ showErrors: false })
    }, AUTO_REFRESH_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [status, selected?.thread?.id, currentUserId])

  async function openThread(threadId) {
    setBusy(true)
    setFeedback('')
    try {
      setSelected(await readHouseholdThread(threadId))
      setReadThreadIds((current) => new Set([...current, threadId]))
    } catch (error) { setFeedback(error.message) }
    finally { setBusy(false) }
  }

  async function performRemoveThread(threadId) {
    setBusy(true)
    setFeedback('')
    try {
      await deleteHouseholdThread(threadId)
      if (selected?.thread?.id === threadId) setSelected(null)
      await refresh()
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
      key: `support-delete-${threadId}`,
      testId: 'support-delete-confirmation',
    })
  }

  async function submitNew(event) {
    event.preventDefault()
    setBusy(true)
    setFeedback('')
    try {
      const created = await createHouseholdThread({ subject, message, screen_name: originScreen, route: originRoute, app_version: getRezzervVersionTag() })
      setSubject('')
      setMessage('')
      await refresh()
      await openThread(created.thread_id)
      setFeedback('Melding verzonden naar de superuser.')
    } catch (error) { setFeedback(error.message) }
    finally { setBusy(false) }
  }

  async function submitReply(event) {
    event.preventDefault()
    if (!selected?.thread?.id) return
    setBusy(true)
    setFeedback('')
    try {
      await replyHouseholdThread(selected.thread.id, reply)
      setReply('')
      setSelected(await readHouseholdThread(selected.thread.id))
      setFeedback('Reactie verzonden.')
    } catch (error) { setFeedback(error.message) }
    finally { setBusy(false) }
  }

  const refreshLabel = lastRefreshedAt
    ? `Laatst ververst: ${lastRefreshedAt.toLocaleTimeString('nl-NL')} · cyclus ${refreshCount}`
    : 'Nog niet ververst'

  return (
    <AppShell title="Meldingen" showExit={false}>
      <div className="rz-support-layout" data-testid="household-support-page">
        <Card>
          <div className="rz-support-toolbar">
            <div><h2>Mijn meldingen</h2><p aria-live="polite" className="rz-support-refresh">{refreshLabel}</p></div>
            <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter op status">
              {STATUSES.map((value) => <option key={value || 'all'} value={value}>{value || 'Alle statussen'}</option>)}
            </select>
          </div>
          <p>Je ziet uitsluitend meldingen die je zelf vanuit het actieve huishouden hebt verzonden.</p>
          {!busy && !threads.length ? <p>Geen meldingen gevonden.</p> : null}
          <div className="rz-support-list">
            {threads.map((thread) => (
              <div key={thread.id} className={`rz-support-thread-row ${isUnread(thread) ? 'rz-support-thread-row--unread' : ''}`}>
                <button type="button" className="rz-support-thread" onClick={() => openThread(thread.id)}>
                  <strong>{thread.subject}</strong>
                  <span>{thread.thread_number} · {thread.status}</span>
                  <span>{thread.origin_screen_name} · {thread.message_count} bericht(en)</span>
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
                <div><h2>{selected.thread.subject}</h2><p>{selected.thread.thread_number} · {selected.thread.status}</p></div>
                <Button variant="secondary" onClick={() => setSelected(null)}>Nieuwe melding</Button>
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
              {Number(selected.thread.reply_allowed) === 1 ? (
                <form onSubmit={submitReply} className="rz-support-form">
                  <label>Reactie<textarea value={reply} onChange={(event) => setReply(event.target.value)} required maxLength={10000} /></label>
                  <Button variant="primary" type="submit" disabled={busy || !reply.trim()}>Versturen</Button>
                </form>
              ) : <p>De superuser heeft antwoorden voor deze melding uitgeschakeld.</p>}
            </>
          ) : (
            <form onSubmit={submitNew} className="rz-support-form">
              <h2>Nieuwe melding</h2>
              <p>Herkomst: <strong>{originScreen}</strong> · <code>{originRoute}</code></p>
              <label>Onderwerp<Input value={subject} onChange={(event) => setSubject(event.target.value)} required maxLength={250} /></label>
              <label>Bericht<textarea value={message} onChange={(event) => setMessage(event.target.value)} required maxLength={10000} /></label>
              <Button variant="primary" type="submit" disabled={busy || !subject.trim() || !message.trim()}>Melding versturen</Button>
            </form>
          )}
          {feedback ? <p className="rz-support-feedback" role="status">{feedback}</p> : null}
        </Card>
      </div>
    </AppShell>
  )
}
