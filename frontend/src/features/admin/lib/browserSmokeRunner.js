const FRAME_ID = 'rezzerv-smoke-runner-frame'
const WAIT_TIMEOUT = 8000
const POLL_INTERVAL = 100

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function waitForCondition(check, timeout = WAIT_TIMEOUT, errorMessage = 'Timeout') {
  const start = Date.now()
  return new Promise((resolve, reject) => {
    function tick() {
      try {
        const result = check()
        if (result) {
          resolve(result)
          return
        }
      } catch {
        // blijf pollen
      }

      if (Date.now() - start >= timeout) {
        reject(new Error(errorMessage))
        return
      }
      window.setTimeout(tick, POLL_INTERVAL)
    }
    tick()
  })
}

function removeExistingFrame() {
  const existing = document.getElementById(FRAME_ID)
  if (existing) existing.remove()
}

function createHiddenFrame() {
  removeExistingFrame()
  const frame = document.createElement('iframe')
  frame.id = FRAME_ID
  frame.title = 'Smoke test runner'
  frame.setAttribute('aria-hidden', 'true')
  Object.assign(frame.style, {
    position: 'fixed',
    left: '-10000px',
    top: '0',
    width: '1280px',
    height: '800px',
    opacity: '0',
    pointerEvents: 'none',
    border: '0',
    background: '#fff',
  })
  document.body.appendChild(frame)
  return frame
}

function getFrameDocument(frame) {
  return frame.contentDocument || frame.contentWindow?.document || null
}

async function navigateFrame(frame, path) {
  await new Promise((resolve, reject) => {
    let settled = false
    const timer = window.setTimeout(() => {
      if (settled) return
      settled = true
      reject(new Error(`Navigatie naar ${path} duurde te lang`))
    }, WAIT_TIMEOUT)

    function handleLoad() {
      if (settled) return
      settled = true
      window.clearTimeout(timer)
      resolve()
    }

    frame.addEventListener('load', handleLoad, { once: true })
    frame.src = path
  })

  await waitForCondition(() => {
    const doc = getFrameDocument(frame)
    return doc && doc.readyState === 'complete'
  }, WAIT_TIMEOUT, `Pagina ${path} werd niet volledig geladen`)

  await delay(150)
}

function queryText(doc, text) {
  return doc?.body?.textContent?.includes(text)
}

function setInputValue(input, value) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
  setter?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

function clickElement(element) {
  element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }))
}

async function runScenario(name, fn, results) {
  try {
    await fn()
    results.push({ name, status: 'passed', error: null })
  } catch (error) {
    results.push({ name, status: 'failed', error: error.message || 'Onbekende fout' })
  }
}

export async function runBrowserSmokeTests() {
  const results = []
  const frame = createHiddenFrame()

  try {
    await runScenario('Login werkt', async () => {
      await navigateFrame(frame, '/login')
      const doc = getFrameDocument(frame)
      const emailInput = await waitForCondition(
        () => doc?.querySelector('input[placeholder="admin@rezzerv.local"]'),
        WAIT_TIMEOUT,
        'E-mailveld niet gevonden op loginpagina'
      )
      const passwordInput = doc.querySelector('input[type="password"]')
      const submitButton = Array.from(doc.querySelectorAll('button')).find((button) => button.textContent?.includes('Inloggen'))
      if (!passwordInput || !submitButton) {
        throw new Error('Loginformulier is onvolledig')
      }
      setInputValue(emailInput, 'admin@rezzerv.local')
      setInputValue(passwordInput, 'Rezzerv123')
      clickElement(submitButton)
      await waitForCondition(
        () => frame.contentWindow?.location?.pathname === '/home',
        WAIT_TIMEOUT,
        'Login leidde niet naar de startpagina'
      )
    }, results)

    await runScenario('Home opent', async () => {
      await waitForCondition(() => {
        const doc = getFrameDocument(frame)
        return queryText(doc, 'Startpagina') && queryText(doc, 'Voorraad') && queryText(doc, 'Instellingen')
      }, WAIT_TIMEOUT, 'Startpagina is niet correct zichtbaar')
    }, results)

    await runScenario('Voorraad opent', async () => {
      await navigateFrame(frame, '/voorraad')
      await waitForCondition(() => {
        const doc = getFrameDocument(frame)
        return queryText(doc, 'Voorraad') && doc?.querySelectorAll('tbody tr')?.length > 0
      }, WAIT_TIMEOUT, 'Voorraadpagina toont geen artikelen')
    }, results)

    await runScenario('Artikeldetail opent vanuit Voorraad', async () => {
      const doc = getFrameDocument(frame)
      const detailLink = doc?.querySelector('tbody tr td:nth-child(2) a')
      const articleName = detailLink?.textContent?.trim()
      if (!detailLink || !articleName) {
        throw new Error('Artikellink in Voorraad kon niet worden gelezen')
      }
      clickElement(detailLink)
      await waitForCondition(() => {
        const detailDoc = getFrameDocument(frame)
        return detailDoc && frame.contentWindow?.location?.pathname.startsWith('/voorraad/') && queryText(detailDoc, `Artikel details: ${articleName}`)
      }, WAIT_TIMEOUT, 'Artikeldetail opende niet vanuit Voorraad')
    }, results)

    await runScenario('Instellingen veldzichtbaarheid opent', async () => {
      await navigateFrame(frame, '/instellingen')
      const doc = getFrameDocument(frame)
      const settingsLink = await waitForCondition(
        () => doc?.querySelector('a[href="/instellingen/artikeldetails/veldzichtbaarheid"]'),
        WAIT_TIMEOUT,
        'Link naar Veldzichtbaarheid niet gevonden'
      )
      clickElement(settingsLink)
      await waitForCondition(() => {
        const detailDoc = getFrameDocument(frame)
        return frame.contentWindow?.location?.pathname === '/instellingen/artikeldetails/veldzichtbaarheid' && queryText(detailDoc, 'Veldzichtbaarheid')
      }, WAIT_TIMEOUT, 'Scherm Veldzichtbaarheid opende niet')
    }, results)
  } finally {
    removeExistingFrame()
  }

  return results
}
