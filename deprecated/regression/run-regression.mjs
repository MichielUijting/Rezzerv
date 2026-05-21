import fs from 'fs'
import fsp from 'fs/promises'
import net from 'net'
import path from 'path'
import { fileURLToPath } from 'url'
import { spawn } from 'child_process'
import { chromium } from '@playwright/test'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const frontendDir = path.resolve(__dirname, '..')
const repoRoot = path.resolve(frontendDir, '..')
const backendDir = path.join(repoRoot, 'backend')
const versionFile = path.join(repoRoot, 'VERSION.txt')
const reportDir = path.join(repoRoot, 'reports', 'regression')
const dynamicPortOffset = 2000 + Math.floor(Math.random() * 3000)
const frontendPort = Number(process.env.REZZERV_FRONTEND_PORT || (15000 + dynamicPortOffset))
const backendPort = Number(process.env.REZZERV_BACKEND_PORT || (18000 + dynamicPortOffset))
const backendUrl = `http://127.0.0.1:${backendPort}`
const frontendUrl = `http://127.0.0.1:${frontendPort}`
const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
const backendLogPath = path.join(reportDir, `backend-${timestamp}.log`)
const frontendLogPath = path.join(reportDir, `frontend-${timestamp}.log`)
const finalJsonPath = path.join(reportDir, 'regression-report.json')
const finalSummaryPath = path.join(reportDir, 'regression-summary.txt')
const rawDbCandidatePaths = [path.join(backendDir, 'rezzerv.db'), path.join(repoRoot, 'rezzerv.db'), path.join(backendDir, 'rezzerv_test_temp.db')]
const pythonBin = process.env.REZZERV_PYTHON_BIN || process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3')
const chromiumExecutable = process.env.REZZERV_CHROMIUM_PATH || (fs.existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined)
const viteBin = path.join(frontendDir, 'node_modules', 'vite', 'bin', 'vite.js')
const venvDir = path.join(backendDir, '.venv')
const venvPython = process.platform === 'win32' ? path.join(venvDir, 'Scripts', 'python.exe') : path.join(venvDir, 'bin', 'python')

const STATE = {
  INIT: 'INIT',
  BUILD: 'BUILD',
  START_BACKEND: 'START_BACKEND',
  WAIT_BACKEND: 'WAIT_BACKEND',
  START_FRONTEND: 'START_FRONTEND',
  WAIT_FRONTEND: 'WAIT_FRONTEND',
  RUN_PLAYWRIGHT: 'RUN_PLAYWRIGHT',
  COLLECT_RESULTS: 'COLLECT_RESULTS',
  DONE: 'DONE',
  FAILED: 'FAILED',
}

function readVersion() { return fs.readFileSync(versionFile, 'utf8').trim() }
function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)) }

async function waitForUrl(url, predicate, timeoutMs, label) {
  const started = Date.now()
  let lastError = null
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url)
      const text = await response.text()
      if (response.ok && predicate(text, response)) return { ok: true, text }
      lastError = new Error(`${label} gaf status ${response.status}`)
    } catch (error) {
      lastError = error
    }
    await sleep(500)
  }
  throw new Error(`${label} niet bereikbaar binnen ${timeoutMs} ms${lastError ? `: ${lastError.message}` : ''}`)
}

async function assertPortAvailable(port, label) {
  await new Promise((resolve, reject) => {
    const server = net.createServer()
    server.once('error', (error) => {
      if (error && error.code === 'EADDRINUSE') {
        reject(new Error(`${label} poort ${port} is al in gebruik. Stop het bestaande proces of zet een andere REZZERV_${label.toUpperCase()}_PORT.`))
      } else {
        reject(error)
      }
    })
    server.once('listening', () => server.close(resolve))
    server.listen(port, '127.0.0.1')
  })
}

function spawnLogged(command, args, options = {}, logPath) {
  const child = spawn(command, args, {
    cwd: options.cwd,
    env: options.env,
    shell: false,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  const logStream = fs.createWriteStream(logPath, { flags: 'a' })
  logStream.write(`[spawn] ${command} ${args.join(' ')}\n`)
  child.stdout.on('data', (chunk) => logStream.write(chunk))
  child.stderr.on('data', (chunk) => logStream.write(chunk))
  child.on('error', (error) => logStream.write(`[spawn-error] ${error.message}\n`))
  child.on('close', (code, signal) => {
    logStream.write(`[spawn-exit] ${code}${signal ? ` signal=${signal}` : ''}\n`)
    logStream.end()
  })
  return child
}

async function runCommand(command, args, options = {}, logPath) {
  await fsp.mkdir(path.dirname(logPath), { recursive: true })
  return new Promise((resolve, reject) => {
    const child = spawnLogged(command, args, options, logPath)
    child.on('error', reject)
    child.on('close', (code) => {
      if (code === 0) resolve()
      else reject(new Error(`${command} ${args.join(' ')} stopte met exitcode ${code}`))
    })
  })
}

async function stopChild(child) {
  if (!child || child.killed) return
  child.kill('SIGTERM')
  await sleep(1000)
  if (!child.killed) child.kill('SIGKILL')
}

async function ensureBackendPython() {
  const installLogPath = path.join(reportDir, `backend-setup-${timestamp}.log`)
  if (!fs.existsSync(venvPython)) {
    await runCommand(pythonBin, ['-m', 'venv', venvDir], { cwd: backendDir, env: { ...process.env } }, installLogPath)
  }
  const probePath = path.join(reportDir, `backend-python-probe-${timestamp}.py`)
  await fsp.writeFile(probePath, 'import fastapi\nimport sqlalchemy\nimport uvicorn\n', 'utf8')
  let ready = false
  try {
    await runCommand(venvPython, [probePath], { cwd: backendDir, env: { ...process.env } }, installLogPath)
    ready = true
  } catch {
    ready = false
  }
  if (!ready) {
    await runCommand(venvPython, ['-m', 'pip', 'install', '-r', 'requirements.txt'], { cwd: backendDir, env: { ...process.env } }, installLogPath)
    await runCommand(venvPython, [probePath], { cwd: backendDir, env: { ...process.env } }, installLogPath)
  }
  return venvPython
}

async function copyBaselineDb() {
  const source = rawDbCandidatePaths.find((candidate) => fs.existsSync(candidate))
  if (!source) throw new Error('Geen baseline sqlite-database gevonden voor regressierun')
  await fsp.mkdir(reportDir, { recursive: true })
  const target = path.join(reportDir, `rezzerv-regression-${timestamp}.db`)
  await fsp.copyFile(source, target)
  return target
}

async function bootstrapAdminSession(page) {
  const password = process.env.REZZERV_REGRESSION_ADMIN_PASSWORD || ['Rezzerv', '123'].join('')
  const loginResponse = await fetch(`${backendUrl}/api/auth/login`, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'admin@rezzerv.local', password }),
  })
  const loginPayload = await loginResponse.json().catch(() => ({}))
  if (!loginResponse.ok || !loginPayload?.token) {
    throw new Error(loginPayload?.detail || loginPayload?.message || `Admin login voor regressierunner mislukte met status ${loginResponse.status}`)
  }
  const token = String(loginPayload.token || '').trim()
  const contextResponse = await fetch(`${backendUrl}/api/auth/context`, {
    headers: { Accept: 'application/json', Authorization: `Bearer ${token}` },
  })
  const contextPayload = await contextResponse.json().catch(() => ({}))
  if (!contextResponse.ok) {
    throw new Error(contextPayload?.detail || contextPayload?.message || `Auth context voor regressierunner mislukte met status ${contextResponse.status}`)
  }
  await page.addInitScript((payload) => {
    try {
      window.localStorage.setItem('rezzerv_token', payload.token)
      window.localStorage.setItem('rezzerv_user_email', payload.email || '')
      if (payload.householdName) window.localStorage.setItem('rezzerv_household_name', payload.householdName)
      window.localStorage.setItem('rezzerv_auth_context', JSON.stringify(payload.context || {}))
      window.sessionStorage.setItem('rezzerv_auth_checked_token', payload.token)
    } catch {}
  }, {
    token,
    email: String(loginPayload?.user?.email || 'admin@rezzerv.local'),
    householdName: String(contextPayload?.active_household_name || ''),
    context: contextPayload,
  })
}

async function runRegressionBrowser() {
  const browser = await chromium.launch({ headless: true, executablePath: chromiumExecutable })
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  const consoleMessages = []
  page.on('console', (message) => consoleMessages.push(`${message.type()}: ${message.text()}`))
  page.on('pageerror', (error) => consoleMessages.push(`pageerror: ${error.message}`))
  try {
    await bootstrapAdminSession(page)
    await page.goto(`${frontendUrl}/regression-runner?ts=${Date.now()}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    if (page.url().includes('/login')) throw new Error(`Regression runner niet bereikbaar: login redirect naar ${page.url()}`)
    if (!page.url().includes('/regression-runner')) throw new Error(`Regression runner niet bereikbaar: onverwachte url ${page.url()}`)
    await page.waitForSelector('[data-testid="regression-runner-page"]', { timeout: 60000 })
    await page.waitForFunction(() => {
      const runtime = window.__rezzervRegressionStatus || window.__REZZERV_REGRESSION_STATUS__ || null
      if (runtime && runtime.state && runtime.state !== 'running') return true
      const el = document.querySelector('[data-testid="regression-runner-status"]')
      if (!el) return false
      const status = el.getAttribute('data-status')
      return status === 'completed' || status === 'failed'
    }, undefined, { timeout: 300000 })
    const jsonText = await page.textContent('[data-testid="regression-runner-json"]')
    if (!jsonText || !jsonText.trim()) throw new Error('Regression runner leverde geen JSON op')
    return JSON.parse(jsonText)
  } catch (error) {
    const statusText = await page.locator('[data-testid="regression-runner-status"]').textContent({ timeout: 1000 }).catch(() => '')
    const jsonText = await page.locator('[data-testid="regression-runner-json"]').textContent({ timeout: 1000 }).catch(() => '')
    throw new Error([
      error.message,
      `url=${page.url()}`,
      `status=${statusText}`,
      `json=${jsonText.slice(0, 1200)}`,
      `console=${consoleMessages.slice(-10).join(' | ')}`,
    ].join('\n'))
  } finally {
    await page.close().catch(() => {})
    await browser.close().catch(() => {})
  }
}

function summarize(fullReport) {
  const lines = []
  lines.push(`Versie: ${fullReport.version}`)
  lines.push(`Build: ${fullReport.build.status}`)
  lines.push(`Health: ${fullReport.health.status}`)
  lines.push(`Regressie: ${fullReport.regression.overall_status}`)
  lines.push(`Totaaloordeel: ${fullReport.overall_status}`)
  lines.push('')
  for (const layer of fullReport.regression.layers || []) {
    lines.push(`${layer.id}: ${layer.status} (${layer.passed_count} geslaagd / ${layer.failed_count} gefaald)`)
    for (const result of layer.results || []) {
      lines.push(`- ${result.status === 'passed' ? 'OK' : 'FAIL'} ${result.name}${result.error ? ` — ${result.error}` : ''}${result.warning ? ` — ${result.warning}` : ''}`)
    }
    lines.push('')
  }
  if (fullReport.regression.fatal_error) lines.push(`Fatale regressiefout: ${fullReport.regression.fatal_error}`)
  return lines.join('\n').trim() + '\n'
}

function createReport(version, dbPath) {
  return {
    version,
    started_at: new Date().toISOString(),
    state: STATE.INIT,
    build: { status: 'pending' },
    health: { status: 'pending' },
    regression: { overall_status: 'pending', layers: [] },
    overall_status: 'running',
    commands: { canonical: process.platform === 'win32' ? 'run-regression.bat' : 'cd frontend && npm run regression' },
    artifacts: {
      report_json: path.relative(repoRoot, finalJsonPath),
      summary_txt: path.relative(repoRoot, finalSummaryPath),
      backend_log: path.relative(repoRoot, backendLogPath),
      frontend_log: path.relative(repoRoot, frontendLogPath),
      database_copy: path.relative(repoRoot, dbPath),
    },
    ports: { backend: backendPort, frontend: frontendPort },
  }
}

async function main() {
  const version = readVersion()
  await fsp.mkdir(reportDir, { recursive: true })
  const dbPath = await copyBaselineDb()
  const report = createReport(version, dbPath)
  let backendProcess = null
  let frontendProcess = null
  try {
    report.state = STATE.BUILD
    await assertPortAvailable(backendPort, 'backend')
    await assertPortAvailable(frontendPort, 'frontend')
    await runCommand(process.execPath, [viteBin, 'build'], { cwd: frontendDir, env: { ...process.env, VITE_REZZERV_VERSION: version } }, frontendLogPath)
    report.build = { status: 'passed', finished_at: new Date().toISOString() }

    report.state = STATE.START_BACKEND
    const backendPython = await ensureBackendPython()
    backendProcess = spawnLogged(backendPython, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(backendPort)], { cwd: backendDir, env: { ...process.env, DATABASE_URL: `sqlite:///${dbPath}`, RECEIPT_STORAGE_ROOT: path.join(reportDir, 'receipts', 'raw') } }, backendLogPath)

    report.state = STATE.WAIT_BACKEND
    await waitForUrl(`${backendUrl}/api/health`, (text) => text.includes('ok'), 120000, 'Backend health')
    report.health = { status: 'passed', checked_at: new Date().toISOString(), url: `${backendUrl}/api/health` }

    report.state = STATE.START_FRONTEND
    frontendProcess = spawnLogged(process.execPath, [viteBin, '--host', '127.0.0.1', '--port', String(frontendPort)], { cwd: frontendDir, env: { ...process.env, VITE_REZZERV_VERSION: version } }, frontendLogPath)

    report.state = STATE.WAIT_FRONTEND
    await waitForUrl(`${frontendUrl}/version.json`, (text) => text.includes(version), 120000, 'Frontend version.json')

    report.state = STATE.RUN_PLAYWRIGHT
    const regression = await runRegressionBrowser()

    report.state = STATE.COLLECT_RESULTS
    report.regression = {
      ...regression,
      layers: Array.isArray(regression.layers) ? regression.layers : [],
      overall_status: regression.overall_status === 'passed' ? 'passed' : 'failed',
    }
    report.overall_status = report.build.status === 'passed' && report.health.status === 'passed' && report.regression.overall_status === 'passed' ? 'passed' : 'failed'
    report.finished_at = new Date().toISOString()
    report.state = report.overall_status === 'passed' ? STATE.DONE : STATE.FAILED
  } catch (error) {
    report.overall_status = 'failed'
    report.finished_at = new Date().toISOString()
    report.state = STATE.FAILED
    if (report.build.status === 'pending') report.build = { status: 'failed', error: error.message }
    else if (report.health.status === 'pending') report.health = { status: 'failed', error: error.message }
    else report.regression = { overall_status: 'failed', layers: [], fatal_error: error.message }
  } finally {
    await stopChild(frontendProcess)
    await stopChild(backendProcess)
    await sleep(500)
  }
  const summary = summarize(report)
  await fsp.writeFile(finalJsonPath, JSON.stringify(report, null, 2), 'utf8')
  await fsp.writeFile(finalSummaryPath, summary, 'utf8')
  process.stdout.write(summary)
  process.exit(report.overall_status === 'passed' ? 0 : 1)
}

main().catch(async (error) => {
  await fsp.mkdir(reportDir, { recursive: true })
  const fallback = { version: fs.existsSync(versionFile) ? readVersion() : 'onbekend', overall_status: 'failed', state: STATE.FAILED, fatal_error: error.message, finished_at: new Date().toISOString() }
  await fsp.writeFile(finalJsonPath, JSON.stringify(fallback, null, 2), 'utf8')
  await fsp.writeFile(finalSummaryPath, `Status: failed\nFatale fout: ${error.message}\n`, 'utf8')
  process.stderr.write(`${error.message}\n`)
  process.exit(1)
})
