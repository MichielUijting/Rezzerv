import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession'
import SettingsArticleGroupsPage from './SettingsArticleGroupsPage'

const STOCK = 'STOCK'
const DIRECT_CONSUMPTION = 'DIRECT_CONSUMPTION'

const GROUP_COLUMN_WIDTHS = [48, 330, 210, 180]
const ARTICLE_COLUMN_WIDTHS = [48, 300, 240, 180]

function normalizeHandling(value) {
  return String(value || '').trim().toUpperCase() === DIRECT_CONSUMPTION
    ? DIRECT_CONSUMPTION
    : STOCK
}

function canManageArticleDefaults(authContext = {}) {
  const displayRole = String(authContext?.display_role || '').trim().toLowerCase()
  const canonicalRole = String(authContext?.role || '').trim().toLowerCase()
  const permissions = authContext?.permissions && typeof authContext.permissions === 'object'
    ? authContext.permissions
    : {}

  return Boolean(
    permissions['articles.manage'] === true
    || displayRole === 'admin'
    || canonicalRole === 'owner'
    || canonicalRole === 'admin'
    || canonicalRole === 'household.owner'
    || canonicalRole === 'household.admin'
  )
}

async function requestJson(url, options = {}) {
  const response = await fetchJsonWithAuth(url, options)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data?.detail || 'Verzoek mislukt')
  return data
}

async function saveHandling(householdId, articleId, checked) {
  const next = checked ? DIRECT_CONSUMPTION : STOCK
  const data = await requestJson(
    `/api/households/${encodeURIComponent(householdId)}/articles/${encodeURIComponent(articleId)}/inventory-handling`,
    {
      method: 'PUT',
      body: JSON.stringify({ default_inventory_handling: next }),
    },
  )
  return normalizeHandling(data?.default_inventory_handling)
}

function HandlingCheckbox({ checked, disabled, busy, label, onChange, error = '' }) {
  return (
    <div style={{ display: 'grid', justifyItems: 'center', gap: 4 }}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled || busy}
        onChange={(event) => onChange(event.target.checked)}
        aria-label={label}
        title={checked ? 'Direct consumeren' : 'Opslaan in voorraad'}
        style={{ accentColor: '#1A3E2B', width: 18, height: 18 }}
      />
      {error ? <span style={{ fontSize: 11, color: '#b42318' }}>{error}</span> : null}
    </div>
  )
}

function ArticleHandlingCell({ householdId, article, initialValue, canManage, onSaved }) {
  const [value, setValue] = useState(() => normalizeHandling(initialValue))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setValue(normalizeHandling(initialValue))
    setError('')
  }, [initialValue])

  async function handleChange(checked) {
    if (!canManage || busy) return
    const previous = value
    setValue(checked ? DIRECT_CONSUMPTION : STOCK)
    setBusy(true)
    setError('')
    try {
      const saved = await saveHandling(householdId, article.id, checked)
      setValue(saved)
      onSaved?.(article.id, saved)
    } catch (saveError) {
      setValue(previous)
      setError(saveError?.message || 'Opslaan mislukt')
    } finally {
      setBusy(false)
    }
  }

  return (
    <HandlingCheckbox
      checked={value === DIRECT_CONSUMPTION}
      disabled={!canManage}
      busy={busy}
      label={`Direct consumeren voor ${article.article_name || 'huishoudartikel'}`}
      onChange={handleChange}
      error={error}
    />
  )
}

function GroupHandlingCell({ householdId, group, articles, defaults, canManage, onSavedMany }) {
  const initialChecked = articles.length > 0 && articles.every(
    (article) => normalizeHandling(defaults[String(article.id)]) === DIRECT_CONSUMPTION,
  )
  const [checked, setChecked] = useState(initialChecked)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setChecked(initialChecked)
    setError('')
  }, [group.id, initialChecked])

  async function handleChange(nextChecked) {
    if (!canManage || busy || articles.length === 0) return
    const previous = checked
    setChecked(nextChecked)
    setBusy(true)
    setError('')
    try {
      const savedEntries = []
      for (const article of articles) {
        const saved = await saveHandling(householdId, article.id, nextChecked)
        savedEntries.push([String(article.id), saved])
      }
      onSavedMany?.(savedEntries)
    } catch (saveError) {
      setChecked(previous)
      setError(saveError?.message || 'Groep opslaan mislukt')
    } finally {
      setBusy(false)
    }
  }

  return (
    <HandlingCheckbox
      checked={checked}
      disabled={!canManage || articles.length === 0}
      busy={busy}
      label={`Alle artikelen in Artikelgroep ${group.name || ''} direct consumeren`}
      onChange={handleChange}
      error={error}
    />
  )
}

function replaceLegacyTerminology(section) {
  if (!section) return
  const walker = document.createTreeWalker(section, NodeFilter.SHOW_TEXT)
  const replacements = [
    ['Voorraadartikelen laden…', 'Huishoudartikelen laden…'],
    ['Geen huishoudelijke voorraadartikelen gevonden.', 'Geen huishoudartikelen gevonden.'],
    ['Geen voorraadartikelen voor deze selectie.', 'Geen huishoudartikelen voor deze selectie.'],
    ['voorraadartikel', 'huishoudartikel'],
  ]
  while (walker.nextNode()) {
    const node = walker.currentNode
    let nextText = node.nodeValue || ''
    replacements.forEach(([from, to]) => {
      nextText = nextText.replaceAll(from, to)
    })
    if (nextText !== node.nodeValue) node.nodeValue = nextText
  }
}

function setFixedGeometry(table, widths) {
  const total = widths.reduce((sum, width) => sum + width, 0)
  table.style.width = `${total}px`
  table.style.minWidth = `${total}px`
  table.style.maxWidth = '100%'
  const cols = table.querySelectorAll('colgroup col')
  cols.forEach((col, index) => {
    if (widths[index]) col.style.width = `${widths[index]}px`
  })
}

function appendColumn(table, width) {
  const colgroup = table.querySelector('colgroup')
  if (colgroup) {
    const col = document.createElement('col')
    col.dataset.inventoryHandlingColumn = 'true'
    col.style.width = `${width}px`
    colgroup.appendChild(col)
  }
  const headerRows = table.querySelectorAll('thead tr')
  if (headerRows[0]) {
    const th = document.createElement('th')
    th.dataset.inventoryHandlingColumn = 'true'
    th.textContent = 'Standaardverwerking'
    th.style.textAlign = 'center'
    headerRows[0].appendChild(th)
  }
  if (headerRows[1]) {
    const th = document.createElement('th')
    th.dataset.inventoryHandlingColumn = 'true'
    headerRows[1].appendChild(th)
  }
}

function InventoryHandlingColumns() {
  const authContext = readStoredAuthContext() || {}
  const householdId = String(authContext?.active_household_id || authContext?.household_id || '').trim()
  const canManage = canManageArticleDefaults(authContext)
  const [groups, setGroups] = useState([])
  const [articles, setArticles] = useState([])
  const [defaults, setDefaults] = useState({})
  const [articleTargets, setArticleTargets] = useState([])
  const [groupTargets, setGroupTargets] = useState([])

  useEffect(() => {
    let cancelled = false
    if (!householdId) return () => { cancelled = true }

    Promise.all([
      requestJson(`/api/article-groups?household_id=${encodeURIComponent(householdId)}`),
      requestJson(`/api/article-groups/household-articles?household_id=${encodeURIComponent(householdId)}`),
    ])
      .then(async ([groupData, articleData]) => {
        const nextGroups = Array.isArray(groupData?.items) ? groupData.items : []
        const nextArticles = Array.isArray(articleData?.items) ? articleData.items : []
        if (cancelled) return
        setGroups(nextGroups)
        setArticles(nextArticles)
        const batch = await requestJson(
          `/api/households/${encodeURIComponent(householdId)}/articles/inventory-handling/batch`,
          {
            method: 'POST',
            body: JSON.stringify({ household_article_ids: nextArticles.map((item) => item.id) }),
          },
        )
        if (cancelled) return
        setDefaults(Object.fromEntries(
          (Array.isArray(batch?.items) ? batch.items : []).map(
            (item) => [String(item.id), normalizeHandling(item.default_inventory_handling)],
          ),
        ))
      })
      .catch(() => {
        if (!cancelled) {
          setGroups([])
          setArticles([])
          setDefaults({})
        }
      })

    return () => { cancelled = true }
  }, [householdId])

  const articlesByName = useMemo(() => {
    const map = new Map()
    articles.forEach((article) => {
      const key = String(article?.article_name || 'Onbekend artikel').trim()
      map.set(key, [...(map.get(key) || []), article])
    })
    return map
  }, [articles])

  const groupsByName = useMemo(() => new Map(
    groups.map((group) => [String(group?.name || '').trim(), group]),
  ), [groups])

  useEffect(() => {
    let scheduled = false
    let disposed = false

    function integrate() {
      if (disposed) return
      const page = document.querySelector('[data-testid="settings-article-groups-page"]')
      const tables = page?.querySelectorAll('table') || []
      if (tables.length < 2) return
      const groupTable = tables[0]
      const articleTable = tables[tables.length - 1]

      if (groupTable.dataset.inventoryHandlingIntegrated !== 'true') {
        groupTable.dataset.inventoryHandlingIntegrated = 'true'
        appendColumn(groupTable, GROUP_COLUMN_WIDTHS[3])
        setFixedGeometry(groupTable, GROUP_COLUMN_WIDTHS)
        const nextGroupTargets = []
        groupTable.querySelectorAll('tbody tr').forEach((row) => {
          const cells = row.querySelectorAll(':scope > td')
          if (cells.length < 3 || cells[0]?.hasAttribute('colspan')) {
            row.querySelector('td[colspan]')?.setAttribute('colspan', '4')
            return
          }
          const input = cells[1]?.querySelector('input')
          const groupName = String(input?.value || cells[1]?.textContent || '').trim()
          const group = groupsByName.get(groupName)
          if (!group) return
          const td = document.createElement('td')
          td.dataset.inventoryHandlingColumn = 'true'
          row.appendChild(td)
          nextGroupTargets.push({ target: td, group })
        })
        setGroupTargets(nextGroupTargets)
      }

      if (articleTable.dataset.inventoryHandlingIntegrated !== 'true') {
        articleTable.dataset.inventoryHandlingIntegrated = 'true'
        appendColumn(articleTable, ARTICLE_COLUMN_WIDTHS[3])
        setFixedGeometry(articleTable, ARTICLE_COLUMN_WIDTHS)
        const usedByName = new Map()
        const nextArticleTargets = []
        articleTable.querySelectorAll('tbody tr').forEach((row) => {
          const cells = row.querySelectorAll(':scope > td')
          if (cells.length < 3 || cells[0]?.hasAttribute('colspan')) {
            row.querySelector('td[colspan]')?.setAttribute('colspan', '4')
            return
          }
          const articleName = String(cells[1]?.textContent || '').trim()
          const candidates = articlesByName.get(articleName) || []
          const used = usedByName.get(articleName) || 0
          const article = candidates[used]
          usedByName.set(articleName, used + 1)
          if (!article) return
          const td = document.createElement('td')
          td.dataset.inventoryHandlingColumn = 'true'
          row.appendChild(td)
          nextArticleTargets.push({ target: td, article })
        })
        setArticleTargets(nextArticleTargets)
      }

      replaceLegacyTerminology(page)
    }

    function schedule() {
      if (scheduled) return
      scheduled = true
      window.requestAnimationFrame(() => {
        scheduled = false
        integrate()
      })
    }

    schedule()
    const observer = new MutationObserver(schedule)
    observer.observe(document.body, { childList: true, subtree: true })

    return () => {
      disposed = true
      observer.disconnect()
      document.querySelectorAll('[data-inventory-handling-column="true"]').forEach((node) => node.remove())
      document.querySelectorAll('table[data-inventory-handling-integrated="true"]').forEach((table) => {
        delete table.dataset.inventoryHandlingIntegrated
      })
      setArticleTargets([])
      setGroupTargets([])
    }
  }, [articlesByName, groupsByName])

  function handleSaved(articleId, value) {
    setDefaults((current) => ({ ...current, [String(articleId)]: value }))
  }

  function handleSavedMany(entries) {
    setDefaults((current) => ({ ...current, ...Object.fromEntries(entries) }))
  }

  return (
    <>
      {groupTargets.map(({ target, group }) => {
        const groupArticles = articles.filter(
          (article) => String(article.article_group_id || '') === String(group.id),
        )
        return createPortal(
          <GroupHandlingCell
            key={String(group.id)}
            householdId={householdId}
            group={group}
            articles={groupArticles}
            defaults={defaults}
            canManage={canManage}
            onSavedMany={handleSavedMany}
          />,
          target,
        )
      })}
      {articleTargets.map(({ target, article }) => createPortal(
        <ArticleHandlingCell
          key={String(article.id)}
          householdId={householdId}
          article={article}
          initialValue={defaults[String(article.id)] || STOCK}
          canManage={canManage}
          onSaved={handleSaved}
        />,
        target,
      ))}
    </>
  )
}

export default function SettingsArticleGroupsWithInventoryHandling() {
  return (
    <>
      <SettingsArticleGroupsPage />
      <InventoryHandlingColumns />
    </>
  )
}
