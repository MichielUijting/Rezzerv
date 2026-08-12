import { useEffect, useMemo, useState } from 'react'
import Header from '../../ui/Header.jsx'
import ScreenCard from '../../ui/ScreenCard.jsx'
import Tabs from '../../ui/Tabs.jsx'
import DataTable from '../../ui/DataTable.jsx'
import Button from '../../ui/Button.jsx'
import Checkbox from '../../ui/Checkbox.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'
import SuperuserOverviewSection from './SuperuserOverviewSection.jsx'
import SuperuserUsageSection from './SuperuserUsageSection.jsx'
import SuperuserUsersSection from './SuperuserUsersSection.jsx'

const TABS = ['Overzicht', 'Huishoudens', 'Gebruikers', 'Gebruik', 'Kassabonnen', 'Meldingen', 'Systeem']
const HOUSEHOLD_SCREENS = [
  ['start', 'Start'], ['kassa', 'Kassa'], ['uitpakken', 'Uitpakken'], ['voorraad', 'Voorraad'],
  ['bijna_op', 'Bijna op'], ['winkelen', 'Winkelen'], ['prognoses', 'Prognoses'], ['diagnose', 'Diagnose'],
]
const ATTRIBUTION_DIAGNOSTIC_SCREENS = [
  ['kassa', 'Kassa'], ['uitpakken', 'Uitpakken'], ['voorraad', 'Voorraadmutaties'],
]
const UNATTRIBUTED_KEY = '__unattributed__'
const PAGE_SIZE = 10

const DETAIL_COLUMN_LABELS = {
  id: 'Technisch ID', retailer: 'Winkelketen', winkel: 'Winkel', purchase_at: 'Aankoopdatum', purchase_date: 'Aankoopdatum',
  status: 'Status', source: 'Bron', imported_at: 'Geïmporteerd op', created_at: 'Aangemaakt op', updated_at: 'Gewijzigd op',
  actor_user_id: 'Technisch gebruiker-ID', actor_attribution_source: 'Herkomst gebruiker', user_id: 'Technisch gebruiker-ID',
  article_id: 'Technisch artikel-ID', household_article_id: 'Technisch huishoudartikel-ID', article_name: 'Artikel',
  article_group_name: 'Artikelgroep', product_type_name: 'Producttype', size: 'Omvang', checked: 'Gekocht', naam: 'Artikel', name: 'Naam',
  artikel: 'Artikel', location_id: 'Technisch locatie-ID', location_label: 'Locatie', event_type: 'Mutatietype', quantity: 'Aantal',
  aantal: 'Aantal', old_quantity: 'Vorig aantal', new_quantity: 'Nieuw aantal', note: 'Notitie', effective_at: 'Effectief op',
  recorded_at: 'Vastgelegd op', receipt_table_id: 'Technisch kassabon-ID', source_reference: 'Bronreferentie', import_status: 'Importstatus',
  approved_at: 'Goedgekeurd op', processed_at: 'Verwerkt op', forecast: 'Prognose', period: 'Periode',
}

const DETAIL_SCREEN_COLUMNS = {
  kassa: ['id', 'retailer', 'winkel', 'purchase_at', 'purchase_date', 'status', 'source', 'imported_at', 'created_at', 'actor_user_id', 'actor_attribution_source'],
  uitpakken: ['id', 'receipt_table_id', 'source_reference', 'status', 'import_status', 'purchase_date', 'approved_at', 'processed_at', 'updated_at', 'created_at', 'actor_user_id', 'actor_attribution_source'],
  voorraad: ['id', 'article_id', 'household_article_id', 'article_name', 'location_id', 'location_label', 'event_type', 'quantity', 'old_quantity', 'new_quantity', 'source', 'note', 'effective_at', 'recorded_at', 'created_at', 'actor_user_id', 'actor_attribution_source'],
  bijna_op: ['id', 'naam', 'aantal', 'household_article_id', 'status', 'updated_at', 'user_id'],
  winkelen: ['id', 'article_name', 'product_type_name', 'size', 'note', 'checked'],
  prognoses: ['id', 'household_article_id', 'article_name', 'forecast', 'quantity', 'period', 'updated_at', 'created_at', 'user_id'],
}

const DUTCH_VALUE_LABELS = {
  active: 'Actief', inactive: 'Inactief', new: 'Nieuw', reviewed: 'Gecontroleerd', purchase: 'Aankoop', pending: 'In behandeling',
  processed: 'Verwerkt', approved: 'Goedgekeurd', rejected: 'Afgewezen', failed: 'Mislukt', ready: 'Gereed', completed: 'Afgerond',
  ignored: 'Genegeerd', manual: 'Handmatig', automatic: 'Automatisch', imported: 'Geïmporteerd', draft: 'Concept', open: 'Open',
  closed: 'Gesloten', owner: 'Eigenaar', admin: 'Beheerder', member: 'Lid', user: 'Gebruiker', viewer: 'Lezer', system: 'Systeem',
  unknown: 'Onbekend', consumption: 'Verbruik', consume: 'Verbruik', correction: 'Correctie', receipt: 'Kassabon', server_session: 'Serversessie',
  request_context: 'Aanvraagcontext', actor_attribution: 'Gebruikersherkomst', legacy: 'Historisch', archived: 'Gearchiveerd',
}

function detailColumnLabel(key) { return DETAIL_COLUMN_LABELS[key] || `Gegeven (${String(key || '').replaceAll('_', ' ')})` }
function formatDateTimeToSeconds(value) {
  if (value == null || value === '') return ''
  const text = String(value)
  const match = text.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})/)
  return match ? `${match[1]} ${match[2]}` : text
}
function dutchValue(value) { if (value == null || value === '') return ''; const text = String(value); return DUTCH_VALUE_LABELS[text.trim().toLowerCase()] || text }
function displayValue(key, value) {
  if (value == null || value === '') return ''
  const normalizedKey = String(key || '').toLowerCase()
  if (normalizedKey === 'checked') return value === true || value === 1 || String(value).trim() === '1' ? 'Ja' : 'Nee'
  if (normalizedKey.endsWith('_at') || normalizedKey.includes('datetime') || normalizedKey.includes('timestamp')) return formatDateTimeToSeconds(value)
  return dutchValue(value)
}

function EmptySection({ title, onOpenHousehold }) {
  if (title === 'Overzicht') return <SuperuserOverviewSection onOpenHousehold={onOpenHousehold} />
  if (title === 'Gebruikers') return <SuperuserUsersSection onOpenHousehold={onOpenHousehold} />
  if (title === 'Gebruik') return <SuperuserUsageSection onOpenHousehold={onOpenHousehold} />
  if (title === 'Meldingen') return <section aria-label="Meldingen" data-testid="superuser-notifications-tab"><h2 style={{ marginTop: 0, fontSize: 20 }}>Meldingen</h2><p>Open het bestaande platformbrede meldingenoverzicht.</p><Button type="button" onClick={() => window.location.assign('/superuser/meldingen')}>Naar Meldingen</Button></section>
  return <section aria-label={title}><h2 style={{ marginTop: 0, fontSize: 20 }}>{title}</h2><p style={{ marginBottom: 0 }}>Dit onderdeel volgt in een volgende Superuser-release.</p></section>
}

function csvValue(value) { return `"${String(value ?? '').replaceAll('"', '""')}"` }
function isTechnicalKey(key) { const normalized = String(key || '').toLowerCase(); return normalized === 'id' || normalized.endsWith('_id') || normalized.includes('uuid') }
function detailRowKey(row, index = 0) { return String(row?.id || row?.receipt_table_id || row?.household_article_id || row?.article_id || row?.source_reference || `detail-${index}`) }

function ReadOnlyTable({ rows, dataTestId, screenKey, showTechnicalIds = false }) {
  const [selectedKeys, setSelectedKeys] = useState([])
  const baseRows = useMemo(() => rows || [], [rows])
  useEffect(() => { const validKeys = new Set(baseRows.map((row, index) => detailRowKey(row, index))); setSelectedKeys((current) => current.filter((key) => validKeys.has(key))) }, [baseRows])
  const dataColumns = useMemo(() => {
    const keys = [...(DETAIL_SCREEN_COLUMNS[screenKey] || [])]
    for (const row of baseRows) for (const key of Object.keys(row || {})) if (!keys.includes(key)) keys.push(key)
    return keys.filter((key) => showTechnicalIds || !isTechnicalKey(key)).map((key, index) => ({ key, header: detailColumnLabel(key), width: index === 0 ? 190 : 145, sortable: true, filterable: true, filterPlaceholder: index === 0 ? 'Zoek' : 'Filter', getValue: (row) => displayValue(key, row?.[key]) }))
  }, [baseRows, screenKey, showTechnicalIds])
  const allSelected = baseRows.length > 0 && baseRows.every((row, index) => selectedKeys.includes(detailRowKey(row, index)))
  const columns = useMemo(() => [{ key: 'selection', header: <Checkbox checked={allSelected} onChange={(event) => { const keys = baseRows.map((row, index) => detailRowKey(row, index)); setSelectedKeys(event.target.checked ? keys : []) }} aria-label="Selecteer alle zichtbare detailregels" />, width: 60, sortable: false, filterable: false, className: 'rz-center' }, ...dataColumns], [allSelected, baseRows, dataColumns])
  const selectedRows = useMemo(() => baseRows.filter((row, index) => selectedKeys.includes(detailRowKey(row, index))), [baseRows, selectedKeys])
  function toggleDetailRow(key, checked) { setSelectedKeys((current) => checked ? [...new Set([...current, key])] : current.filter((item) => item !== key)) }
  function exportSelectedRows() {
    if (selectedRows.length === 0 || dataColumns.length === 0) return
    const rowsForExport = [dataColumns.map((column) => column.header), ...selectedRows.map((row) => dataColumns.map((column) => column.getValue(row)))]
    const csv = `\uFEFF${rowsForExport.map((row) => row.map(csvValue).join(';')).join('\r\n')}`
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' }); const url = URL.createObjectURL(blob); const link = document.createElement('a')
    link.href = url; link.download = `${dataTestId || 'superuser'}-geselecteerde-rijen.csv`; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url)
  }
  return <DataTable columns={columns} data={baseRows} dataTestId={dataTestId} emptyMessage="Geen actieve gegevens beschikbaar voor de geselecteerde categorieën in dit onderdeel." defaultSort={dataColumns[0] ? { key: dataColumns[0].key, direction: 'asc' } : null} pagination pageSize={PAGE_SIZE} paginationActions={<Button type="button" onClick={exportSelectedRows} disabled={selectedRows.length === 0}>Exporteren</Button>} getRowKey={(row, index) => detailRowKey(row, index)} renderRow={(row, index) => { const key = detailRowKey(row, index); return <tr key={key}><td className="rz-center"><Checkbox checked={selectedKeys.includes(key)} onChange={(event) => toggleDetailRow(key, event.target.checked)} aria-label={`Selecteer detailregel ${index + 1}`} /></td>{dataColumns.map((column) => <td key={column.key}>{column.getValue(row)}</td>)}</tr> }} />
}

function memberKey(member, index = 0) { return String(member?.selection_key || member?.user_id || member?.email || `member-${index}`) }
function rowActorUserId(row) { if (row?.actor_user_id != null && String(row.actor_user_id).trim()) return String(row.actor_user_id); if (row?.user_id != null && String(row.user_id).trim()) return String(row.user_id); return '' }

function Diagnostics({ data, selectionLabel, attributionSummary }) {
  const d = data || {}
  const cards = [['Kassabonnen', d.receipt_count ?? 0], ['Voorraadregels', d.inventory_count ?? 0], ['Voorraadevents', d.inventory_event_count ?? 0], ['Uitpakbatches', d.unpack_batch_count ?? 0], ['Actorattributies', d.actor_attribution_count ?? 0], ['Negatieve voorraad', d.negative_inventory_count ?? 0]]
  const columns = useMemo(() => [
    { key: 'onderdeel', header: 'Onderdeel', width: 220, sortable: true, filterable: true, filterPlaceholder: 'Zoek', getValue: (row) => row.onderdeel },
    { key: 'totaal', header: 'Totaal', width: 110, sortable: true, align: 'right', getValue: (row) => row.totaal },
    { key: 'met_gebruiker', header: 'Met gebruiker', width: 140, sortable: true, align: 'right', getValue: (row) => row.met_gebruiker },
    { key: 'niet_herleidbaar', header: 'Niet herleidbaar', width: 150, sortable: true, align: 'right', getValue: (row) => row.niet_herleidbaar },
  ], [])
  return <div><p style={{ marginTop: 0 }}>Gebruikersfilter: <strong>{selectionLabel}</strong>. Diagnosecijfers zijn huishoudbreed en worden niet als gebruikersspecifiek gepresenteerd.</p><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, marginBottom: 18 }}>{cards.map(([label, value]) => <div key={label} style={{ border: '1px solid #d4ddd4', borderRadius: 6, padding: 12 }}><div style={{ fontSize: 13 }}>{label}</div><div style={{ fontSize: 24 }}>{value}</div></div>)}</div><h3 style={{ fontSize: 17, marginBottom: 8 }}>Gebruikersherkomst</h3><p style={{ marginTop: 0 }}>Deze tabel laat zien hoeveel actieve verwerkingen wel en niet aan een gebruiker kunnen worden herleid.</p><DataTable columns={columns} data={attributionSummary || []} dataTestId="superuser-attribution-diagnostics-table" getRowKey={(row) => row.key} defaultSort={{ key: 'onderdeel', direction: 'asc' }} emptyMessage="Gebruikersherkomst wordt geladen of is niet beschikbaar." pagination pageSize={PAGE_SIZE} /><p><strong>Laatste kassabon:</strong> {d.last_receipt_at ? formatDateTimeToSeconds(d.last_receipt_at) : '—'}</p><p><strong>Laatste voorraadmutatie:</strong> {d.last_inventory_event_at ? formatDateTimeToSeconds(d.last_inventory_event_at) : '—'}</p>{(d.flags || []).length > 0 && <div>{d.flags.map((flag) => <p key={flag.code}>⚠ {flag.label}</p>)}</div>}</div>
}

function HouseholdInspector({ householdId }) {
  const [overview, setOverview] = useState(null), [selectedUserKeys, setSelectedUserKeys] = useState([]), [attributionSummary, setAttributionSummary] = useState([]), [screen, setScreen] = useState('diagnose'), [screenData, setScreenData] = useState(null), [showTechnicalIds, setShowTechnicalIds] = useState(false), [error, setError] = useState('')
  useEffect(() => { let cancelled = false; fetchJsonWithAuth(`/api/superuser/households/${encodeURIComponent(householdId)}`).then(async (response) => { const payload = await response.json().catch(() => ({})); if (!response.ok) throw new Error(payload?.detail || 'Huishouden kon niet worden geopend.'); if (cancelled) return; const members = payload.members || []; setOverview(payload); setSelectedUserKeys([...members.map((member, index) => memberKey(member, index)), UNATTRIBUTED_KEY]) }).catch((e) => { if (!cancelled) setError(String(e?.message || e)) }); return () => { cancelled = true } }, [householdId])
  useEffect(() => { let cancelled = false; if (!overview) return () => {}; Promise.all(ATTRIBUTION_DIAGNOSTIC_SCREENS.map(async ([key, label]) => { const response = await fetchJsonWithAuth(`/api/superuser/households/${encodeURIComponent(householdId)}/screens/${key}`); const payload = await response.json().catch(() => ({})); if (!response.ok) throw new Error(payload?.detail || `Diagnose voor ${label} kon niet worden geladen.`); const rows = payload.rows || []; const metGebruiker = rows.filter((row) => Boolean(rowActorUserId(row))).length; return { key, onderdeel: label, totaal: rows.length, met_gebruiker: metGebruiker, niet_herleidbaar: rows.length - metGebruiker } })).then((rows) => { if (!cancelled) setAttributionSummary(rows) }).catch(() => { if (!cancelled) setAttributionSummary([]) }); return () => { cancelled = true } }, [householdId, overview])
  useEffect(() => { let cancelled = false; if (!overview) return () => {}; if (screen === 'diagnose') { setScreenData({ diagnostics: overview.diagnostics, rows: [] }); return () => {} } fetchJsonWithAuth(`/api/superuser/households/${encodeURIComponent(householdId)}/screens/${screen}`).then(async (response) => { const payload = await response.json().catch(() => ({})); if (!response.ok) throw new Error(payload?.detail || 'Read-only scherm kon niet worden geladen.'); if (!cancelled) setScreenData(payload) }).catch((e) => { if (!cancelled) setError(String(e?.message || e)) }); return () => { cancelled = true } }, [householdId, overview, screen])
  const members = overview?.members || []
  const selectionRows = useMemo(() => [...members, { selection_key: UNATTRIBUTED_KEY, email: 'Niet aan gebruiker herleidbaar', role: '—', status: '—', unattributed: true }], [members])
  const allSelectionRowsSelected = selectionRows.length > 0 && selectionRows.every((member, index) => selectedUserKeys.includes(memberKey(member, index)))
  const memberColumns = useMemo(() => [{ key: 'selection', header: <Checkbox checked={allSelectionRowsSelected} onChange={(event) => setSelectedUserKeys(event.target.checked ? selectionRows.map((member, index) => memberKey(member, index)) : [])} aria-label="Selecteer alle gebruikerscategorieën" />, width: 60, sortable: false, filterable: false, className: 'rz-center' }, { key: 'email', header: 'Gebruiker', width: 300, sortable: true, filterable: true, filterPlaceholder: 'Zoek', getValue: (row) => row.email || row.user_id || '' }, { key: 'role', header: 'Rol', width: 150, sortable: true, filterable: true, filterPlaceholder: 'Filter', getValue: (row) => dutchValue(row.role) }, { key: 'status', header: 'Status', width: 130, sortable: true, filterable: true, filterPlaceholder: 'Filter', getValue: (row) => dutchValue(row.status) }], [allSelectionRowsSelected, selectionRows])
  const realMemberKeys = useMemo(() => members.map((member, index) => memberKey(member, index)), [members])
  const allUsersSelected = realMemberKeys.length > 0 && realMemberKeys.every((key) => selectedUserKeys.includes(key))
  const includeUnattributed = selectedUserKeys.includes(UNATTRIBUTED_KEY)
  const fullSelection = allUsersSelected && includeUnattributed
  const selectedUserIds = useMemo(() => new Set(members.filter((member, index) => selectedUserKeys.includes(memberKey(member, index))).map((member) => String(member?.user_id || '')).filter(Boolean)), [members, selectedUserKeys])
  const selectedMembers = useMemo(() => members.filter((member, index) => selectedUserKeys.includes(memberKey(member, index))), [members, selectedUserKeys])
  const selectionParts = []; if (allUsersSelected) selectionParts.push('alle gebruikers'); else if (selectedMembers.length > 0) selectionParts.push(selectedMembers.map((member) => member.email || member.user_id || 'Onbekende gebruiker').join(', ')); if (includeUnattributed) selectionParts.push('niet aan gebruiker herleidbaar'); const selectionLabel = selectionParts.length > 0 ? selectionParts.join(' + ') : 'geen categorie geselecteerd'
  const visibleRows = useMemo(() => { const rows = screenData?.rows || []; if (fullSelection) return rows; return rows.filter((row) => { const actorUserId = rowActorUserId(row); if (!actorUserId) return includeUnattributed; return selectedUserIds.has(actorUserId) }) }, [screenData, fullSelection, includeUnattributed, selectedUserIds])
  function toggleUser(key) { setSelectedUserKeys((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key]) }
  if (error) return <div role="alert">{error}</div>; if (!overview) return <div role="status">Huishouden wordt geladen…</div>
  const name = overview.household?.name || overview.household?.household_id || householdId, activeScreenLabel = HOUSEHOLD_SCREENS.find(([key]) => key === screen)?.[1] || 'Diagnose'
  function renderScreenContent() { if (screen === 'diagnose') return <Diagnostics data={overview.diagnostics} selectionLabel={selectionLabel} attributionSummary={attributionSummary} />; if (!screenData) return <p>Gegevens worden geladen…</p>; return <><div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, alignItems: 'center', marginBottom: 12 }}><span>Filter: <strong>{selectionLabel}</strong>.</span><span>Voorkomens: <strong>alleen actief</strong>.</span><label style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}><Checkbox checked={showTechnicalIds} onChange={(event) => setShowTechnicalIds(event.target.checked)} aria-label="Technische ID's tonen" />Technische ID's: {showTechnicalIds ? 'Aan' : 'Uit'}</label></div><ReadOnlyTable rows={visibleRows} dataTestId={`superuser-${screen}-table`} screenKey={screen} showTechnicalIds={showTechnicalIds} /></> }
  return <section data-testid="superuser-household-inspector"><div style={{ border: '1px solid #d4ddd4', background: '#f7faf7', padding: 12, borderRadius: 6, marginBottom: 14 }}><strong>Superuser — Huishouden {name} — Alleen lezen</strong></div><h2 style={{ fontSize: 20, marginBottom: 8 }}>Gebruikers</h2><DataTable columns={memberColumns} data={selectionRows} dataTestId="superuser-household-members-table" getRowKey={(row, index) => memberKey(row, index)} defaultSort={{ key: 'email', direction: 'asc' }} emptyMessage="Geen gebruikers gevonden voor dit huishouden." pagination pageSize={PAGE_SIZE} renderRow={(member, index) => { const key = memberKey(member, index), checked = selectedUserKeys.includes(key); return <tr key={key}><td className="rz-center"><Checkbox checked={checked} onChange={() => toggleUser(key)} aria-label={`Toon details voor ${member.email || member.user_id || index + 1}`} /></td><td>{member.email || member.user_id || ''}</td><td>{dutchValue(member.role)}</td><td>{dutchValue(member.status)}</td></tr> }} /><div style={{ marginTop: 24 }}><Tabs tabs={HOUSEHOLD_SCREENS.map(([, label]) => label)} activeTab={activeScreenLabel} onTabChange={(label) => setScreen(HOUSEHOLD_SCREENS.find(([, candidate]) => candidate === label)?.[0] || 'diagnose')}>{() => renderScreenContent()}</Tabs></div></section>
}

function countOpenNotifications(signal) { const match = String(signal || '').match(/(\d+) open melding/i); return match ? Number(match[1]) : 0 }
function HouseholdsSection({ selectedId, onSelectHousehold }) {
  const [items, setItems] = useState([]), [loading, setLoading] = useState(false), [error, setError] = useState('')
  useEffect(() => { let cancelled = false; setLoading(true); Promise.all([fetchJsonWithAuth('/api/superuser/households'), fetchJsonWithAuth('/api/superuser/overview')]).then(async ([householdsResponse, overviewResponse]) => { const householdPayload = await householdsResponse.json().catch(() => ({})), overviewPayload = await overviewResponse.json().catch(() => ({})); if (!householdsResponse.ok) throw new Error(householdPayload?.detail || 'Huishoudens konden niet worden geladen.'); const attention = new Map((overviewResponse.ok ? overviewPayload.attention_items || [] : []).map((item) => [String(item.household_id), item])); const enriched = await Promise.all((householdPayload.items || []).map(async (item) => { const householdId = String(item.household_id || ''); let members = []; try { const response = await fetchJsonWithAuth(`/api/superuser/households/${encodeURIComponent(householdId)}`); const payload = await response.json().catch(() => ({})); if (response.ok) members = payload.members || [] } catch { members = [] } const activeMembers = members.filter((member) => String(member.status || 'active').toLowerCase() === 'active').length; const archivedMembers = Math.max(0, members.length - activeMembers); const attentionItem = attention.get(householdId) || {}; return { ...item, active_member_count: activeMembers, archived_member_count: archivedMembers, attention_signal: attentionItem.signal || '', attention_count: attentionItem.signal_count || 0, open_notification_count: countOpenNotifications(attentionItem.signal) } })); if (!cancelled) setItems(enriched) }).catch((e) => { if (!cancelled) setError(String(e?.message || e)) }).finally(() => { if (!cancelled) setLoading(false) }); return () => { cancelled = true } }, [])
  const columns = useMemo(() => [
    { key: 'name', header: 'Huishouden', width: 230, sortable: true, filterable: true, filterPlaceholder: 'Zoek', getValue: (row) => row.name || row.household_id || '' },
    { key: 'status', header: 'Status', width: 120, sortable: true, filterable: true, filterPlaceholder: 'Filter', getValue: (row) => dutchValue(row.status || 'active') },
    { key: 'active_member_count', header: 'Actieve gebruikers', width: 145, sortable: true, align: 'right', getValue: (row) => row.active_member_count ?? 0 },
    { key: 'archived_member_count', header: 'Gearchiveerd', width: 130, sortable: true, align: 'right', getValue: (row) => row.archived_member_count ?? 0 },
    { key: 'created_at', header: 'Aangemaakt op', width: 180, sortable: true, filterable: true, filterPlaceholder: 'Filter', getValue: (row) => row.created_at ? formatDateTimeToSeconds(row.created_at) : '—' },
    { key: 'last_active_at', header: 'Laatst actief', width: 180, sortable: true, filterable: true, filterPlaceholder: 'Filter', getValue: (row) => row.last_active_at ? formatDateTimeToSeconds(row.last_active_at) : '—' },
    { key: 'receipt_count', header: 'Kassabonnen', width: 120, sortable: true, align: 'right', getValue: (row) => row.receipt_count ?? 0 },
    { key: 'open_notification_count', header: 'Open meldingen', width: 135, sortable: true, align: 'right', getValue: (row) => row.open_notification_count ?? 0 },
    { key: 'attention_signal', header: 'Aandacht vereist', width: 320, sortable: true, filterable: true, filterPlaceholder: 'Filter', getValue: (row) => row.attention_signal || '—' },
  ], [])
  if (selectedId) return <HouseholdInspector householdId={selectedId} />
  return <section aria-label="Huishoudens" data-testid="superuser-households"><h2 style={{ marginTop: 0, fontSize: 20 }}>Huishoudens</h2><p style={{ marginTop: 0 }}>Dubbelklik op een huishouden om het alleen-lezen te bekijken.</p>{error && <div role="alert">{error}</div>}{loading ? <p>Huishoudens worden geladen…</p> : <DataTable columns={columns} data={items} dataTestId="superuser-households-table" getRowKey={(row) => row.household_id} defaultSort={{ key: 'name', direction: 'asc' }} emptyMessage="Geen huishoudens gevonden." pagination pageSize={PAGE_SIZE} renderRow={(item) => <tr key={item.household_id} onDoubleClick={() => onSelectHousehold(item.household_id)} title="Dubbelklik om dit huishouden alleen-lezen te bekijken">{columns.map((column) => <td key={column.key} className={column.align === 'right' ? 'rz-num' : ''}>{String(column.getValue(item) ?? '')}</td>)}</tr>} />}</section>
}

export default function SuperuserDashboardPage() {
  const [access, setAccess] = useState(null), [error, setError] = useState(''), [activeTab, setActiveTab] = useState('Overzicht'), [selectedHouseholdId, setSelectedHouseholdId] = useState(null)
  useEffect(() => { let cancelled = false; fetchJsonWithAuth('/api/superuser/bootstrap').then(async (response) => { const payload = await response.json().catch(() => ({})); if (!response.ok) throw new Error(payload?.detail || 'Superuser-toegang kon niet worden gevalideerd.'); if (cancelled) return; setAccess(payload); await fetchJsonWithAuth('/api/superuser/audit/open', { method: 'POST' }) }).catch((e) => { if (!cancelled) setError(String(e?.message || e || 'Superuser-toegang mislukt.')) }); return () => { cancelled = true } }, [])
  function handleTopTabChange(tab) { setActiveTab(tab); if (tab === 'Huishoudens') setSelectedHouseholdId(null) }
  function openHouseholdFromOverview(householdId) { setSelectedHouseholdId(householdId); setActiveTab('Huishoudens') }
  return <div className="rz-screen" data-testid="superuser-dashboard"><Header title="Rezzerv Beheercentrum" /><div className="rz-content"><div className="rz-content-inner"><ScreenCard fullWidth>{error ? <div role="alert">{error}</div> : !access ? <div role="status">Superuser-toegang wordt gecontroleerd…</div> : <><div role="status" aria-label="Superuser alleen-lezen status" style={{ marginBottom: 16, padding: '10px 12px', border: '1px solid #d4ddd4', borderRadius: 6, background: '#f7faf7' }}><strong>Superuser</strong> — beheercentrum. Toegang: <strong>alleen lezen</strong>.</div><Tabs tabs={TABS} activeTab={activeTab} onTabChange={handleTopTabChange}>{(tab) => tab === 'Huishoudens' ? <HouseholdsSection selectedId={selectedHouseholdId} onSelectHousehold={setSelectedHouseholdId} /> : <EmptySection title={tab} onOpenHousehold={openHouseholdFromOverview} />}</Tabs></>}</ScreenCard></div></div></div>
}
