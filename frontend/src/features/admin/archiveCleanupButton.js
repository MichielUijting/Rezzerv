const BUTTON_ID = 'rezzerv-admin-purge-archived-receipts-button'
const MESSAGE_ID = 'rezzerv-admin-purge-archived-receipts-message'

function getAuthHeaders() {
  const token = localStorage.getItem('rezzerv_token') || ''
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function isAdminPath() {
  return window.location.pathname === '/admin'
}

function setMessage(text) {
  const message = document.getElementById(MESSAGE_ID)
  if (message) message.textContent = text || ''
}

async function purgeArchivedReceipts(button) {
  const confirmed = window.confirm('Weet je zeker dat je gearchiveerde kassabondata definitief wilt verwijderen? Actieve kassabonnen blijven behouden.')
  if (!confirmed) return

  button.disabled = true
  const originalLabel = button.textContent
  button.textContent = 'Archief opruimen…'
  setMessage('Gearchiveerde kassabondata wordt verwijderd…')

  try {
    const response = await fetch('/api/dev/receipts/purge-archived', {
      method: 'POST',
      headers: getAuthHeaders(),
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(data.detail || 'Gearchiveerde kassabondata kon niet worden verwijderd.')
    }
    const deleted = data.deleted || {}
    const after = data.after || {}
    setMessage(`Archief opgeschoond: ${deleted.receipt_tables || 0} kassabon(nen), ${deleted.raw_receipts || 0} bronbestand(en), ${deleted.receipt_table_lines || 0} regel(s). Actief over: ${after.active_receipt_tables ?? 'onbekend'}.`)
  } catch (error) {
    setMessage(error?.message || 'Gearchiveerde kassabondata kon niet worden verwijderd.')
  } finally {
    button.disabled = false
    button.textContent = originalLabel
  }
}

function installArchiveCleanupButton() {
  if (!isAdminPath()) return
  if (document.getElementById(BUTTON_ID)) return

  const adminPage = document.querySelector('[data-testid="admin-page"]')
  if (!adminPage) return

  const firstActions = adminPage.querySelector('.rz-admin-panel .rz-admin-actions')
  if (!firstActions) return

  const button = document.createElement('button')
  button.id = BUTTON_ID
  button.type = 'button'
  button.className = 'rz-btn rz-btn--secondary rz-button rz-button--secondary'
  button.textContent = 'Verwijder gearchiveerde kassabonnen'
  button.setAttribute('data-testid', 'admin-purge-archived-receipts-button')
  button.addEventListener('click', () => purgeArchivedReceipts(button))
  firstActions.appendChild(button)

  const message = document.createElement('div')
  message.id = MESSAGE_ID
  message.className = 'rz-admin-message'
  message.setAttribute('data-testid', 'admin-purge-archived-receipts-message')
  firstActions.parentElement?.appendChild(message)
}

function scheduleInstall() {
  window.setTimeout(installArchiveCleanupButton, 0)
  window.setTimeout(installArchiveCleanupButton, 250)
  window.setTimeout(installArchiveCleanupButton, 1000)
}

if (typeof window !== 'undefined') {
  scheduleInstall()
  window.addEventListener('popstate', scheduleInstall)
  const observer = new MutationObserver(scheduleInstall)
  observer.observe(document.documentElement, { childList: true, subtree: true })
}
