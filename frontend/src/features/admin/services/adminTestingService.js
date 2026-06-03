class AdminTestingServiceError extends Error {
  constructor(message, status = null, details = null) {
    super(message)
    this.name = 'AdminTestingServiceError'
    this.status = status
    this.details = details
  }
}

const EMPTY_STATUS = {
  test_type: null,
  status: 'idle',
  last_run_at: null,
  passed_count: 0,
  failed_count: 0,
  blocked_count: 0,
  last_error: null,
}

const EMPTY_REPORT = {
  test_type: null,
  last_run_at: null,
  blocked_count: 0,
  results: [],
}

async function parseJsonSafely(response) {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    throw new AdminTestingServiceError('Ongeldige JSON ontvangen van de server.', response.status)
  }
}

function getAuthHeaders() {
  const token = localStorage.getItem('rezzerv_token') || ''
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'include',
    ...options,
    headers: {
      Accept: 'application/json',
      ...getAuthHeaders(),
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  })

  const data = await parseJsonSafely(response).catch(() => null)
  if (!response.ok) {
    throw new AdminTestingServiceError(
      data?.detail || data?.message || 'Testactie mislukt.',
      response.status,
      data
    )
  }
  return data
}

function normalizeStatus(data) {
  return {
    ...EMPTY_STATUS,
    ...(data || {}),
  }
}

function normalizeReport(data) {
  return {
    ...EMPTY_REPORT,
    ...(data || {}),
    results: Array.isArray(data?.results) ? data.results : [],
  }
}

export async function runSmokeTests() {
  return request('/api/dev/run-smoke-tests', { method: 'POST', body: '{}' })
}

export async function runRegressionTests() {
  return request('/api/dev/run-regression-tests', { method: 'POST', body: '{}' })
}

export async function runLayer1Tests() {
  return request('/api/dev/run-layer1-tests', { method: 'POST', body: '{}' })
}

export async function runLayer2Tests() {
  return request('/api/dev/run-layer2-tests', { method: 'POST', body: '{}' })
}

export async function runLayer3Tests() {
  return request('/api/dev/run-layer3-tests', { method: 'POST', body: '{}' })
}


export async function runAlmostOutSelfTest() {
  return request('/api/dev/regression/almost-out-self-test', { method: 'POST', body: '{}' })
}

export async function fetchLatestTestStatus() {
  const data = await request('/api/dev/test-status', { method: 'GET' })
  return normalizeStatus(data)
}

export async function fetchLatestTestReport() {
  const data = await request('/api/dev/test-report/latest', { method: 'GET' })
  return normalizeReport(data)
}

export { AdminTestingServiceError, EMPTY_STATUS, EMPTY_REPORT }

export async function submitTestResults(testType, results) {
  return request('/api/dev/test-report', {
    method: 'POST',
    body: JSON.stringify({ test_type: testType, results }),
  })
}

export async function runParsingFixtureTests() {
  return request('/api/dev/run-parsing-fixture-tests', { method: 'POST', body: '{}' })
}

export async function runParsingRawTests() {
  return request('/api/dev/run-parsing-raw-tests', { method: 'POST', body: '{}' })
}
