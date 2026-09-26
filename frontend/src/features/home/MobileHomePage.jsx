import { useEffect, useMemo, useState } from 'react'
import { listHouseholdThreads } from '../support/supportApi.js'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import './mobileHome.css'

const DEFAULT_ORDER = ['kassa', 'kassabonnen', 'winkelen', 'voorraad', 'bijna-op', 'catalogus', 'meldingen']
const ACTION_ICONS = {
  kassa: <svg className="rz-illustrated-icon" viewBox="0 0 64 64" aria-hidden="true"><path fill="#455a64" d="M10 31h44l5 25H5z"/><rect x="16" y="10" width="32" height="20" rx="5" fill="#90a4ae"/><rect x="21" y="14" width="22" height="9" rx="2" fill="#b2f2e9"/><rect x="26" y="34" width="24" height="14" rx="3" fill="#cfd8dc"/><g fill="#ff9f43"><circle cx="31" cy="39" r="2.5"/><circle cx="38" cy="39" r="2.5"/><circle cx="45" cy="39" r="2.5"/><circle cx="31" cy="45" r="2.5"/><circle cx="38" cy="45" r="2.5"/><circle cx="45" cy="45" r="2.5"/></g><rect x="14" y="50" width="36" height="4" rx="2" fill="#263238"/></svg>,
  kassabonnen: <svg className="rz-illustrated-icon" viewBox="0 0 64 64" aria-hidden="true"><defs><clipPath id="rz-bag-body"><path d="M13 22h38l-4 36H17z"/></clipPath></defs><path fill="#f5c46f" d="M13 22h38l-4 36H17z"/><g clipPath="url(#rz-bag-body)"><rect x="11" y="29" width="42" height="7" fill="#ef5350"/><rect x="11" y="36" width="42" height="7" fill="#42a5f5"/><rect x="11" y="43" width="42" height="7" fill="#f6c344"/></g><path d="M23 24v-5c0-12 18-12 18 0v5" fill="none" stroke="#9c5d16" strokeWidth="5" strokeLinecap="round"/><path d="M13 22h38l-4 36H17z" fill="none" stroke="#d69738" strokeWidth="2"/></svg>,
  winkelen: <svg className="rz-illustrated-icon" viewBox="0 0 64 64" aria-hidden="true"><path fill="#ef3e3e" d="M9 27h46l-5 28H14z"/><path d="M18 29L28 12m18 17L36 12" stroke="#37474f" strokeWidth="6" strokeLinecap="round"/><path d="M21 36v11m11-11v11m11-11v11" stroke="#ffd4d4" strokeWidth="4" strokeLinecap="round"/></svg>,
  voorraad: <svg className="rz-illustrated-icon" viewBox="0 0 64 64" aria-hidden="true"><g stroke="#607d8b" strokeWidth="2"><rect x="20" y="7" width="27" height="20" rx="4" fill="#eceff1"/><rect x="6" y="31" width="27" height="22" rx="4" fill="#9ccc65"/><rect x="34" y="31" width="24" height="22" rx="4" fill="#ffb74d"/></g><path fill="#42a5f5" d="M20 7h27v7H20z"/><path fill="#7cb342" d="M6 31h27v7H6z"/><path fill="#fb8c00" d="M34 31h24v7H34z"/><g fill="#546e7a"><rect x="29" y="17" width="9" height="4" rx="2"/><rect x="15" y="42" width="9" height="4" rx="2"/><rect x="42" y="42" width="9" height="4" rx="2"/></g></svg>,
  'bijna-op': <svg className="rz-illustrated-icon" viewBox="0 0 64 64" aria-hidden="true"><path fill="#ffc83d" d="M13 46h38c-5-6-7-12-7-23a12 12 0 0 0-24 0c0 11-2 17-7 23z"/><circle cx="32" cy="50" r="5" fill="#e58b00"/><circle cx="48" cy="17" r="11" fill="#f44336"/><path d="M48 11v8m0 4h.1" stroke="#fff" strokeWidth="4" strokeLinecap="round"/><path d="M8 17l-5-4m8 14H4m52-10l5-4" stroke="#ff9800" strokeWidth="4" strokeLinecap="round"/></svg>,
  catalogus: <svg className="rz-illustrated-icon" viewBox="0 0 64 64" aria-hidden="true"><path fill="#7e57c2" d="M4 12c11-4 21-1 28 6 7-7 17-10 28-6v43c-11-4-21-1-28 6-7-7-17-10-28-6z"/><path fill="#fff" d="M8 16c9-2 16 0 22 5v33c-6-5-13-7-22-5zm48 0c-9-2-16 0-22 5v33c6-5 13-7 22-5z"/><circle cx="19" cy="29" r="6" fill="#ef5350"/><path fill="#43a047" d="M18 21c2-4 5-5 8-4-2 4-5 5-8 4z"/><rect x="39" y="23" width="10" height="15" rx="3" fill="#42a5f5"/><path stroke="#b0bec5" strokeWidth="2" d="M12 41h14m12 2h14"/></svg>,
  meldingen: <svg className="rz-illustrated-icon" viewBox="0 0 64 64" aria-hidden="true"><rect x="4" y="19" width="56" height="26" rx="8" fill="#ef3e3e"/><text x="32" y="36" textAnchor="middle" fontSize="13" fontWeight="900" fill="#fff">NIEUWS</text></svg>,
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
