import { useEffect, useMemo, useState } from 'react'
import { listHouseholdThreads } from '../support/supportApi.js'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import './mobileHome.css'

const DEFAULT_ORDER = ['kassa', 'kassabonnen', 'winkelen', 'voorraad', 'bijna-op', 'catalogus', 'meldingen']
const ACTION_ICONS = {
  kassa: <span className="rz-play-icon rz-play-icon--register" aria-hidden="true"><span className="rz-register-display" /><span className="rz-register-paper" /><span className="rz-register-keys">•••<br />•••</span><span className="rz-register-drawer" /></span>,
  kassabonnen: <span className="rz-play-icon rz-play-icon--bag" aria-hidden="true"><span className="rz-bag-handle" /><span className="rz-bag-body" /></span>,
  winkelen: <span className="rz-play-icon rz-play-icon--basket" aria-hidden="true"><span className="rz-basket-handles" /><span className="rz-basket-body" /></span>,
  voorraad: <span className="rz-play-icon rz-play-icon--boxes" aria-hidden="true"><i /><i /><i /></span>,
  'bijna-op': <span className="rz-play-icon rz-play-icon--alert" aria-hidden="true"><span className="rz-alert-bell">●</span><strong>!</strong></span>,
  catalogus: <span className="rz-play-icon rz-play-icon--book" aria-hidden="true"><span>🍎</span><span>▤</span></span>,
  meldingen: <span className="rz-play-icon rz-play-icon--news" aria-hidden="true"><span className="rz-news-horn" /><strong>NIEUWS</strong></span>,
}
const META = {
  kassa: { label: 'Kassa', detail: 'Kassabon scannen', icon: ACTION_ICONS.kassa, tone: 'mint' },
  kassabonnen: { label: 'Uitpakken', detail: 'Artikelen opruimen', icon: ACTION_ICONS.kassabonnen, tone: 'orange' },
  winkelen: { label: 'Boodschappen', detail: 'Bekijk je boodschappenlijst', icon: ACTION_ICONS.winkelen, tone: 'red' },
  voorraad: { label: 'Voorraad', detail: 'Bekijk je voorraad', icon: ACTION_ICONS.voorraad, tone: 'blue' },
  'bijna-op': { label: 'Bijna op', detail: 'Bekijk wat bijna op is', icon: ACTION_ICONS['bijna-op'], tone: 'yellow' },
  catalogus: { label: 'Catalogus', detail: 'Bekijk de productcatalogus', icon: ACTION_ICONS.catalogus, tone: 'purple' },
  meldingen: { label: 'Meldingen', detail: 'Bekijk je meldingen', icon: ACTION_ICONS.meldingen, tone: 'blue' },
}
function identityKey(context) { return String(context?.user_id || context?.email || 'anonymous').trim().toLowerCase() }
function storageKey(context) { return 'inhuis-mobile-home-order:' + identityKey(context) }
function readPersonalOrder(context) {
  try { const parsed = JSON.parse(window.localStorage.getItem(storageKey(context)) || '[]'); return Array.isArray(parsed) ? parsed.map(String) : [] } catch { return [] }
}
function firstName(context) {
  const explicit = String(context?.first_name || '').trim()
  if (explicit) return explicit
  const candidate = String(context?.email || '').split('@')[0].trim().split(/[._-]+/)[0]
  if (!candidate) return ''
  return candidate.charAt(0).toUpperCase() + candidate.slice(1)
}
function InHuisWordmark() {
  return <span className="rz-inhuis-wordmark" aria-label="InHuis"><span className="rz-inhuis-wordmark-in">In</span><span className="rz-inhuis-wordmark-huis">Huis</span></span>
}
function reorder(keys, key, direction) {
  const index = keys.indexOf(key), target = index + direction
  if (index < 0 || target < 0 || target >= keys.length) return keys
  const next = [...keys]; [next[index], next[target]] = [next[target], next[index]]; return next
}
export default function MobileHomePage({ context, navigation, welcomeText = 'Fijn dat je er weer bent.', onOpenTile, onExit }) {
  const availableTiles = useMemo(() => {
    const map = new Map([...navigation.primaryTiles, ...navigation.moreTiles].filter((tile) => tile?.clickable).map((tile) => [tile.key, tile]))
    map.delete('locaties')
    return [...map.values()]
  }, [navigation])
  const availableKeys = useMemo(() => availableTiles.map((tile) => tile.key), [availableTiles])
  const [order, setOrder] = useState(() => readPersonalOrder(context))
  const [editing, setEditing] = useState(false)
  const [openNotifications, setOpenNotifications] = useState(null)
  useEffect(() => { setOrder(readPersonalOrder(context)) }, [context?.user_id, context?.email])
  useEffect(() => {
    let active = true
    listHouseholdThreads('Open').then((payload) => { if (active) setOpenNotifications(Array.isArray(payload?.items) ? payload.items.length : 0) }).catch(() => { if (active) setOpenNotifications(null) })
    return () => { active = false }
  }, [context?.active_household_id, context?.user_id])
  const orderedTiles = useMemo(() => {
    const rank = [...order, ...DEFAULT_ORDER, ...availableKeys].filter((key, index, all) => all.indexOf(key) === index)
    const byKey = new Map(availableTiles.map((tile) => [tile.key, tile]))
    return rank.filter((key) => byKey.has(key)).map((key) => byKey.get(key))
  }, [availableTiles, availableKeys, order])
  function persist(nextKeys) { setOrder(nextKeys); try { window.localStorage.setItem(storageKey(context), JSON.stringify(nextKeys)) } catch {} }
  function move(key, direction) { persist(reorder(orderedTiles.map((tile) => tile.key), key, direction)) }
  const name = firstName(context) || 'gebruiker', primary = orderedTiles.slice(0, 4), more = orderedTiles.slice(4)
  if (editing) return <main className="rz-mobile-home" data-testid="mobile-home-reorder">
    <header className="rz-mobile-home-edit-header"><button type="button" onClick={() => setEditing(false)}>Terug</button><strong>Volgorde aanpassen</strong><button type="button" onClick={() => setEditing(false)}>Gereed</button></header>
    <section className="rz-mobile-home-inner"><p className="rz-mobile-home-intro">Bepaal zelf de volgorde van de acties op je startscherm. Deze volgorde wordt voor jou bewaard voor een volgende sessie op dit apparaat.</p>
      <div className="rz-mobile-home-reorder-list" aria-label="Volgorde acties">{orderedTiles.map((tile, index) => {
        const meta = META[tile.key] || { label: tile.label, icon: ACTION_ICONS.catalogus, tone: 'green' }
        return <div className="rz-mobile-home-reorder-row" key={tile.key}><span className="rz-mobile-home-drag" aria-hidden="true">⠿</span><span className={`rz-mobile-home-icon rz-mobile-home-icon--${meta.tone || 'green'}`} aria-hidden="true">{meta.icon}</span><strong>{meta.label}</strong><span className="rz-mobile-home-reorder-controls"><button type="button" aria-label={meta.label + ' omhoog'} disabled={index === 0} onClick={() => move(tile.key, -1)}>↑</button><button type="button" aria-label={meta.label + ' omlaag'} disabled={index === orderedTiles.length - 1} onClick={() => move(tile.key, 1)}>↓</button></span></div>
      })}</div>
    </section>
  </main>
  return <main className="rz-mobile-home" data-testid="mobile-home-page"><MobileModuleHeader title="Startpagina" testId="mobile-home-header" showBack onBack={onExit} backLabel="Terug" /><section className="rz-mobile-home-inner">
    <h1 className="rz-mobile-home-welcome">Welkom {name} <InHuisWordmark /></h1><p className="rz-mobile-home-subtitle">{welcomeText}</p>
    <button type="button" className="rz-mobile-home-notifications" onClick={() => onOpenTile({ key: 'meldingen', clickable: true })}><span className="rz-mobile-home-notification-icon" aria-hidden="true">{ACTION_ICONS.meldingen}</span><span><strong>{openNotifications === null ? 'Openstaande meldingen' : openNotifications + ' openstaande melding' + (openNotifications === 1 ? '' : 'en')}</strong><small>Bekijk wat aandacht vraagt</small></span><span aria-hidden="true">›</span></button>
    <div className="rz-mobile-home-section-title"><h2>Wat wil je doen?</h2><button type="button" onClick={() => setEditing(true)} data-testid="mobile-home-customize">⚙ Aanpassen</button></div>
    <div className="rz-mobile-home-primary-actions">{primary.map((tile) => { const meta = META[tile.key] || { label: tile.label, detail: '', icon: '•' }; return <button type="button" className="rz-mobile-home-action-card" key={tile.key} onClick={() => onOpenTile(tile)} data-testid={'mobile-home-action-' + tile.key}><span className={`rz-mobile-home-icon rz-mobile-home-icon--${meta.tone || 'green'}`} aria-hidden="true">{meta.icon}</span><span><strong>{meta.label}</strong><small>{meta.detail}</small></span><span aria-hidden="true">›</span></button> })}</div>
    {more.length ? <section className="rz-mobile-home-more"><h2>Meer acties</h2>{more.map((tile) => { const meta = META[tile.key] || { label: tile.label }; return <button type="button" key={tile.key} onClick={() => onOpenTile(tile)}><span>{meta.label}</span><span aria-hidden="true">›</span></button> })}</section> : null}
  </section></main>
}
