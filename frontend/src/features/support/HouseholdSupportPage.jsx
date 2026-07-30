import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import AppShell from '../../app/AppShell.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import Input from '../../ui/Input.jsx'
import { getRezzervVersionTag } from '../../ui/version.js'
import {
  createHouseholdThread,
  listHouseholdThreads,
  readHouseholdThread,
  replyHouseholdThread,
} from './supportApi.js'

const STATUSES = ['', 'Open', 'In behandeling', 'Gesloten']

export default function HouseholdSupportPage() {
  const location = useLocation()
  const query = useMemo(() => new URLSearchParams(location.search), [location.search])
  const originRoute = query.get('from') || '/meldingen'
  const originScreen = query.get('screen') || 'Rezzerv'

  const [threads, setThreads] = useState([])
  const [selected, setSelected] = useState(null)
  const [status, setStatus] = useState('')
  const [subject, setSubject] = useState('')
  const [message, setMessage] = useState('')
  const [reply, setReply] = useState('')
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState('')

  async function refresh() {
    setBusy(true)
    setFeedback('')
    try {
      const data = await listHouseholdThreads(status)
      setThreads(data?.items || [])
      if (selected?.thread?.id) {
        const detail = await readHouseholdThread(selected.thread.id)
        setSelected(detail)
      }
    } catch (error) {
      setFeedback(error.message)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { refresh() }, [status])

  useEffect(() => {
    if (query.get('new') === '1') {
      setSelected(null)
      setSubject('')
      setMessage('')
      setFeedback('')
    }
  }, [location.search])

  async function openThread(threadId) {
    setBusy(true)
    setFeedback('')
    try { setSelected(await readHouseholdThread(threadId)) }
    catch (error) { setFeedback(error.message) }
    finally { setBusy(false) }
  }

  async function submitNew(event) {
    event.preventDefault()
    setBusy(true)
    setFeedback('')
    try {
      const created = await createHouseholdThread({
        subject,
        message,
        screen_name: originScreen,
        route: originRoute,
        app_version: getRezzervVersionTag(),
      })
      setSubject('')
      setMessage('')
      await refresh()
      await openThread(created.thread_id)
      setFeedback('Melding verzonden naar de superuser.')
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
      await replyHouseholdThread(selected.thread.id, reply)
      setReply('')
      setSelected(await readHouseholdThread(selected.thread.id))
      await refresh()
      setFeedback('Reactie verzonden.')
    } catch (error) {
      setFeedback(error.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AppShell title="Meldingen" showExit={false}>
      <div className="rz-support-layout" data-testid="household-support-page">
        <Card>
          <div className="rz-support-toolbar">
            <h2>Mijn meldingen</h2>
            <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter op status">
              {STATUSES.map((value) => <option key={value || 'all'} value={value}>{value || 'Alle statussen'}</option>)}
            </select>
          </div>
          {busy && !threads.length ? <p>Bezig met laden…</p> : null}
          {!busy && !threads.length ? <p>Geen meldingen gevonden.</p> : null}
          <div className="rz-support-list">
            {threads.map((thread) => (
              <button key={thread.id} type="button" className="rz-support-thread" onClick={() => openThread(thread.id)}>
                <strong>{thread.subject}</strong>
                <span>{thread.thread_number} · {thread.status}</span>
                <span>{thread.origin_screen_name} · {thread.message_count} bericht(en)</span>
              </button>
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
