const FIXTURE_KEY = 'rezzerv_layer1_fixture'
const LAYER2_FIXTURE_KEY = 'rezzerv_layer2_fixture'
const LAYER3_FIXTURE_KEY = 'rezzerv_layer3_fixture'
const PROGRESS_KEY = 'rezzerv_regression_progress'

function getAuthHeaders() {
  try {
    const token = window.localStorage.getItem('rezzerv_token') || ''
    return token ? { Authorization: `Bearer ${token}` } : {}
  } catch {
    return {}
  }
}

function clearRunnerLocalState() {
  try {
    window.localStorage.removeItem(FIXTURE_KEY)
    window.localStorage.removeItem(LAYER2_FIXTURE_KEY)
    window.localStorage.removeItem(LAYER3_FIXTURE_KEY)
    window.localStorage.removeItem(PROGRESS_KEY)
  } catch {
    // negeer opslagfouten
  }
}

async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
      ...(options.headers || {}),
    },
    ...options,
  })
  const text = await response.text()
  const data = text ? JSON.parse(text) : null
  if (!response.ok) throw new Error(data?.detail || data?.message || `${path} gaf status ${response.status}`)
  return data
}

function buildStoredFixture(resetInfo, receiptFixture) {
  return {
    articleId: resetInfo?.inventory_fixture?.articleId || resetInfo?.inventory_fixture?.article_id || null,
    articleName: resetInfo?.inventory_fixture?.articleName || resetInfo?.inventory_fixture?.article_name || null,
    inventoryId: resetInfo?.inventory_fixture?.inventoryId || resetInfo?.inventory_fixture?.inventory_id || null,
    batchId: receiptFixture?.batchId || receiptFixture?.batch_id || null,
    completeLineId: receiptFixture?.completeLineId || receiptFixture?.complete_line_id || null,
    incompleteLineId: receiptFixture?.incompleteLineId || receiptFixture?.incomplete_line_id || null,
    batchMatchText: 'Jumbo',
    completeLineLabel: 'Magere yoghurt',
    incompleteLineLabel: 'Appelsap',
    connectionId: receiptFixture?.connectionId || receiptFixture?.connection_id || null,
    latestBatchId: receiptFixture?.latestBatchId || receiptFixture?.latest_batch_id || receiptFixture?.batchId || receiptFixture?.batch_id || null,
  }
}

function storeRegressionFixtures(resetInfo, receiptFixture) {
  const nextFixture = buildStoredFixture(resetInfo, receiptFixture)
  try {
    const serialized = JSON.stringify(nextFixture)
    window.localStorage.setItem(FIXTURE_KEY, serialized)
    window.localStorage.setItem(LAYER2_FIXTURE_KEY, serialized)
    window.localStorage.setItem(LAYER3_FIXTURE_KEY, serialized)
  } catch {
    // negeer opslagfouten
  }
  return nextFixture
}

export async function resetRegressionDataset() {
  clearRunnerLocalState()
  const resetInfo = await requestJson('/api/dev/regression/reset', { method: 'POST', body: '{}' })
  const receiptFixture = await requestJson('/api/dev/generate-layer1-receipt-fixture', { method: 'POST', body: '{}' })
  const storedFixture = storeRegressionFixtures(resetInfo, receiptFixture)
  return { resetInfo, receiptFixture, storedFixture }
}
