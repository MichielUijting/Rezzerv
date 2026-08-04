import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession'
import SettingsArticleGroupsPage from './SettingsArticleGroupsPage'

const STOCK = 'STOCK'
const DIRECT_CONSUMPTION = 'DIRECT_CONSUMPTION'
const COLUMN_WIDTH = 260

const OPTIONS = [
  { value: STOCK, label: 'Opslaan in voorraad' },
  { value: DIRECT_CONSUMPTION, label: 'Direct consumeren' },
]

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

function InventoryHandlingCell({ householdId, articleId, initialValue, canManage, onSaved }) {
  const [value, setValue] = useState(() => normalizeHandling(initialValue))
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setValue(normalizeHandling(initialValue))
    setError('')
  }, [initialValue])

  async function handleChange(event) {
    const previous = value
    const next = normalizeHandling(event.target.value)
    if (!canManage || !articleId || next === previous) return

    setValue(next)
    setIsSaving(true)
    setError('')
    try {
      const data = await requestJson(
        `/api/households/${encodeURIComponent(householdId)}/articles/${encodeURIComponent(articleId)}/inventory-handling`,
        {
          method: 'PUT',
          body: JSON.stringify({ default_inventory_handling: next }),
        },
      )
      const saved = normalizeHandling(data?.default_inventory_handling)
      setValue(saved)
      onSaved?.(articleId, saved)
    } catch (saveError) {
      setValue(previous)
      setError(saveError?.message || 'Opslaan mislukt')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div style={{ display: 'grid', gap: 4 }}>
      <select
        className="rz-input rz-inline-input"
        value={value}
        onChange={handleChange}
        disabled={!canManage || isSaving}
        aria-label={`Standaardverwerking huishoudartikel ${articleId}`}
        data-testid={`article-inventory-handling-${articleId}`}
      >
        {OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
      {!canManage ? <span style={{ fontSize: 12, color: '#667085' }}>Alleen beheerder kan wijzigen</span> : null}
      {error ? <span style={{ fontSize: 12, color: '#b42318' }}>{error}</span> : null}
    </div>
  )
}

function replaceLegacyTerminology(section) {
  if (!section) return
  const walker = document.createTreeWalker(section, NodeFilter.SHOW_TEXT)
  const replacements = [
    ['Voorraadartikelen laden…', 'Huishoudartikelen laden…'],
    ['Geen huishoudelijke voorraadartikelen gevonden.', 'Geen huishoudartikelen gevonden.'],
    ['Geen voorraadartikelen voor deze selectie.', 'Geen huishoudartikelen voor deze selectie.'],
  ]
  while (walker.nextNode()) {
    const node = walker.currentNode
    let nextText = node.nodeValue || ''
    replacements.forEach(([from, to]) => {
      nextText = nextText.replace(from, to)
    })
    if (nextText !== node.nodeValue) node.nodeValue = nextText
  }
}

function InventoryHandlingColumn() {
  const authContext = readStoredAuthContext() || {}
  const householdId = String(authContext?.active_household_id || authContext?.household_id || '').trim()
  const canManage = canManageArticleDefaults(authContext)
  const [articles, setArticles] = useState([])
  const [defaults, setDefaults] = useState({})
  const [targets, setTargets] = useState([])

  useEffect(() => {
    let cancelled = false
    if (!householdId) return () => { cancelled = true }

    Promise.all([
      requestJson(`/api/article-groups/household-articles?household_id=${encodeURIComponent(householdId)}`),
    ])
      .then(async ([articleData]) => {
        const items = Array.isArray(articleData?.items) ? articleData.items : []
        if (cancelled) return
        setArticles(items)
        const batch = await requestJson(
          `/api/households/${encodeURIComponent(householdId)}/articles/inventory-handling/batch`,
          {
            method: 'POST',
            body: JSON.stringify({ household_article_ids: items.map((item) => item.id) }),
          },
        )
        if (cancelled) return
        const nextDefaults = Object.fromEntries(
          (Array.isArray(batch?.items) ? batch.items : []).map((item) => [String(item.id), normalizeHandling(item.default_inventory_handling)]),
        )
        setDefaults(nextDefaults)
      })
      .catch(() => {
        if (!cancelled) {
          setArticles([])
          setDefaults({})
        }
      })

    return () => { cancelled = true }
  }, [householdId])

  const articlesByName = useMemo(() => {
    const map = new Map()
    articles
      .slice()
      .sort((a, b) => String(a?.article_name || '').localeCompare(String(b?.article_name || ''), 'nl'))
      .forEach((article) => {
        const key = String(article?.article_name || 'Onbekend artikel').trim()
        const list = map.get(key) || []
        list.push(article)
        map.set(key, list)
      })
    return map
  }, [articles])

  useEffect(() => {
    let scheduled = false
    let disposed = false

    function integrateColumn() {
      if (disposed) return
      const page = document.querySelector('[data-testid="settings-article-groups-page"]')
      if (!page) return
      const tables = page.querySelectorAll('table')
      const table = tables[tables.length - 1]
      if (!table || table.dataset.inventoryHandlingIntegrated === 'true') {
        replaceLegacyTerminology(page)
        return
      }

      table.dataset.inventoryHandlingIntegrated = 'true'
      const originalWidth = table.style.width
      const originalMinWidth = table.style.minWidth
      table.dataset.inventoryHandlingOriginalWidth = originalWidth
      table.dataset.inventoryHandlingOriginalMinWidth = originalMinWidth
      const parsedWidth = Number.parseInt(originalWidth, 10)
      if (Number.isFinite(parsedWidth)) {
        table.style.width = `${parsedWidth + COLUMN_WIDTH}px`
        table.style.minWidth = `${parsedWidth + COLUMN_WIDTH}px`
      }

      const colgroup = table.querySelector('colgroup')
      if (colgroup) {
        const col = document.createElement('col')
        col.dataset.inventoryHandlingColumn = 'true'
        col.style.width = `${COLUMN_WIDTH}px`
        colgroup.appendChild(col)
      }

      const headerRows = table.querySelectorAll('thead tr')
      if (headerRows[0]) {
        const th = document.createElement('th')
        th.dataset.inventoryHandlingColumn = 'true'
        th.textContent = 'Standaardverwerking'
        headerRows[0].appendChild(th)
      }
      if (headerRows[1]) {
        const th = document.createElement('th')
        th.dataset.inventoryHandlingColumn = 'true'
        headerRows[1].appendChild(th)
      }

      const usedByName = new Map()
      const nextTargets = []
      table.querySelectorAll('tbody tr').forEach((row) => {
        const cells = row.querySelectorAll(':scope > td')
        if (cells.length < 3 || cells[0]?.hasAttribute('colspan')) {
          const colspanCell = row.querySelector('td[colspan]')
          if (colspanCell) colspanCell.setAttribute('colspan', '4')
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
        td.dataset.householdArticleId = String(article.id)
        row.appendChild(td)
        nextTargets.push({ target: td, article })
      })

      replaceLegacyTerminology(page)
      setTargets(nextTargets)
    }

    function scheduleIntegration() {
      if (scheduled) return
      scheduled = true
      window.requestAnimationFrame(() => {
        scheduled = false
        integrateColumn()
      })
    }

    scheduleIntegration()
    const observer = new MutationObserver(() => {
      const page = document.querySelector('[data-testid="settings-article-groups-page"]')
      const tables = page?.querySelectorAll('table') || []
      const table = tables[tables.length - 1]
      if (table && table.dataset.inventoryHandlingIntegrated !== 'true') scheduleIntegration()
      replaceLegacyTerminology(page)
    })
    observer.observe(document.body, { childList: true, subtree: true })

    return () => {
      disposed = true
      observer.disconnect()
      document.querySelectorAll('[data-inventory-handling-column="true"]').forEach((node) => node.remove())
      const integratedTable = document.querySelector('table[data-inventory-handling-integrated="true"]')
      if (integratedTable) {
        integratedTable.style.width = integratedTable.dataset.inventoryHandlingOriginalWidth || ''
        integratedTable.style.minWidth = integratedTable.dataset.inventoryHandlingOriginalMinWidth || ''
        delete integratedTable.dataset.inventoryHandlingIntegrated
      }
      setTargets([])
    }
  }, [articlesByName])

  function handleSaved(articleId, value) {
    setDefaults((current) => ({ ...current, [String(articleId)]: value }))
  }

  return targets.map(({ target, article }) => createPortal(
    <InventoryHandlingCell
      key={String(article.id)}
      householdId={householdId}
      articleId={String(article.id)}
      initialValue={defaults[String(article.id)] || STOCK}
      canManage={canManage}
      onSaved={handleSaved}
    />,
    target,
  ))
}

export default function SettingsArticleGroupsWithInventoryHandling() {
  return (
    <>
      <SettingsArticleGroupsPage />
      <InventoryHandlingColumn />
    </>
  )
}
