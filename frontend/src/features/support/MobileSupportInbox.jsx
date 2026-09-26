import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import Button from '../../ui/Button.jsx'
import Input from '../../ui/Input.jsx'
import { createHouseholdThread, listHouseholdThreads, listHouseholdNotifications, markHouseholdNotificationRead } from './supportApi.js'
import { getRezzervVersionTag } from '../../ui/version.js'
import './mobileSupportInbox.css'

const FILTERS = [['all','Alles'],['messages','Berichten'],['inhuis','Inhuis']]

function stamp(value) {
  if (!value) return ''
  const date = new Date(value)
  return date.toLocaleString('nl-NL', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export default function MobileSupportInbox({ onOpenThread }) {
  const navigate = useNavigate()
  const [filter, setFilter] = useState('all')
  const [threads, setThreads] = useState([])
  const [notifications, setNotifications] = useState([])
  const [error, setError] = useState('')
  const [composing, setComposing] = useState(false)
  const [subject, setSubject] = useState('')
  const [message, setMessage] = useState('')

  async function refresh() {
    try {
      const [messageData, notificationData] = await Promise.all([listHouseholdThreads(''), listHouseholdNotifications()])
      setThreads(messageData?.items || [])
      setNotifications(notificationData?.items || [])
      setError('')
    } catch (exc) { setError(exc.message) }
  }

  useEffect(() => {
    refresh()
    const timer = window.setInterval(refresh, 3000)
    return () => window.clearInterval(timer)
  }, [])

  const items = useMemo(() => {
    const messages = threads.map((thread) => ({
      id: 'message-' + thread.id, kind: 'messages', sourceId: thread.id,
      title: thread.subject, detail: thread.status, category: 'Superuser',
      createdAt: thread.updated_at, unread: false,
    }))
    const inhuis = notifications.map((item) => ({
      id: 'inhuis-' + item.id, kind: 'inhuis', sourceId: item.id,
      title: item.title, detail: item.message, category: item.category || 'Inhuis',
      createdAt: item.created_at, unread: !item.read_at, severity: item.severity, targetRoute: item.target_route,
    }))
    return [...messages, ...inhuis]
      .filter((item) => filter === 'all' || item.kind === filter)
      .sort((a,b) => new Date(b.createdAt || 0) - new Date(a.createdAt || 0))
  }, [filter, notifications, threads])

  const unreadCount = notifications.filter((item) => !item.read_at).length

  async function submitNew(event) {
    event.preventDefault()
    try {
      const created = await createHouseholdThread({ subject, message, screen_name: 'Meldingen', route: '/meldingen', app_version: getRezzervVersionTag() })
      setSubject('')
      setMessage('')
      setComposing(false)
      await refresh()
      onOpenThread(created.thread_id)
    } catch (exc) { setError(exc.message) }
  }

  async function openItem(item) {
    if (item.kind === 'messages') return onOpenThread(item.sourceId)
    await markHouseholdNotificationRead(item.sourceId)
    setNotifications((current) => current.map((entry) => entry.id === item.sourceId ? { ...entry, read_at: new Date().toISOString() } : entry))
    if (item.targetRoute) navigate(item.targetRoute)
  }

  return (
    <div className="rz-mobile-support-screen" data-testid="mobile-support-inbox">
      <MobileModuleHeader title="Meldingen" testId="mobile-support-header" />
      <main className="rz-mobile-support-content">
        <div className="rz-mobile-support-summary">
          <strong>{unreadCount} ongelezen</strong>
          <Button type="button" variant="primary" onClick={() => setComposing(true)}>+ Nieuw bericht</Button>
        </div>
        {composing ? (
          <form className="rz-mobile-support-compose" onSubmit={submitNew}>
            <strong>Nieuw bericht aan Superuser</strong>
            <label>Onderwerp<Input value={subject} onChange={(event) => setSubject(event.target.value)} required maxLength={250} /></label>
            <label>Bericht<textarea value={message} onChange={(event) => setMessage(event.target.value)} required maxLength={10000} /></label>
            <div><Button type="submit" variant="primary" disabled={!subject.trim() || !message.trim()}>Versturen</Button> <Button type="button" variant="secondary" onClick={() => setComposing(false)}>Annuleren</Button></div>
          </form>
        ) : null}
        <div className="rz-mobile-support-filters" role="tablist" aria-label="Meldingen filteren">
          {FILTERS.map(([key,label]) => <button key={key} type="button" className={filter === key ? 'is-active' : ''} onClick={() => setFilter(key)}>{label}</button>)}
        </div>
        {error ? <p role="status">{error}</p> : null}
        <div className="rz-mobile-support-list">
          {items.map((item) => (
            <button key={item.id} type="button" className={'rz-mobile-support-card rz-mobile-support-card--' + (item.severity || 'message')} onClick={() => openItem(item)}>
              <span className="rz-mobile-support-meta">{item.kind === 'messages' ? 'BERICHT · ' : 'INHUIS · '}{String(item.category).toUpperCase()} · {stamp(item.createdAt)}</span>
              <span className="rz-mobile-support-title">{item.title}{item.unread ? <i aria-label="Ongelezen" /> : null}</span>
              <span className="rz-mobile-support-detail">{item.detail}</span>
              <span className="rz-mobile-support-link">{item.kind === 'messages' ? 'Naar gesprek ›' : 'Bekijken ›'}</span>
            </button>
          ))}
          {!items.length ? <div className="rz-mobile-support-empty"><strong>Geen nieuwe meldingen</strong><span>Alles is op dit moment bijgewerkt.</span></div> : null}
        </div>
      </main>
    </div>
  )
}
