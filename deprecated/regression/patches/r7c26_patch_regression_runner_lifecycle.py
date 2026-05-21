from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'frontend' / 'scripts' / 'run-regression.mjs'
s = path.read_text(encoding='utf-8')

# R7c-25 prerequisites: dynamic ports, python probe, Windows npm spawn wrapper retained.
s = s.replace(
    'const frontendPort = Number(process.env.REZZERV_FRONTEND_PORT || 5174)\nconst backendPort = Number(process.env.REZZERV_BACKEND_PORT || 8001)',
    'const dynamicPortOffset = 2000 + Math.floor(Math.random() * 3000)\nconst frontendPort = Number(process.env.REZZERV_FRONTEND_PORT || (15000 + dynamicPortOffset))\nconst backendPort = Number(process.env.REZZERV_BACKEND_PORT || (18000 + dynamicPortOffset))',
)

old_probe = "try { await runCommand(venvPython, ['-c', 'import fastapi; import sqlalchemy; import uvicorn'], { cwd: backendDir, env: { ...process.env } }, installLogPath); ready = true } catch { ready = false }"
new_probe = "const probePath = path.join(reportDir, `backend-python-probe-${timestamp}.py`)\n  await fsp.writeFile(probePath, 'import fastapi\\nimport sqlalchemy\\nimport uvicorn\\n', 'utf8')\n  try { await runCommand(venvPython, [probePath], { cwd: backendDir, env: { ...process.env } }, installLogPath); ready = true } catch { ready = false }"
s = s.replace(old_probe, new_probe)
s = s.replace('}, { timeout: 300000 })', '}, undefined, { timeout: 300000 })')

insert_after = "async function runCommand(command, args, options = {}, logPath) {\n  await fsp.mkdir(path.dirname(logPath), { recursive: true })\n  return new Promise((resolve, reject) => {\n    const child = spawnLogged(command, args, options, logPath)\n    child.on('error', reject)\n    child.on('close', (code) => { if (code === 0) resolve(); else reject(new Error(`${command} ${args.join(' ')} stopte met exitcode ${code}`)) })\n  })\n}\n"
helper = r'''
async function runBestEffort(command, args, options = {}, logPath) {
  try {
    await fsp.mkdir(path.dirname(logPath), { recursive: true })
    await new Promise((resolve) => {
      const child = spawnLogged(command, args, options, logPath)
      child.on('error', () => resolve())
      child.on('close', () => resolve())
    })
  } catch {}
}

async function freePort(port, logPath) {
  if (process.platform !== 'win32') return
  await runBestEffort('powershell.exe', [
    '-NoProfile',
    '-ExecutionPolicy',
    'Bypass',
    '-Command',
    `$ErrorActionPreference='SilentlyContinue'; $pids=(Get-NetTCPConnection -LocalPort ${port}).OwningProcess | Sort-Object -Unique; foreach($pid in $pids){ if($pid -and $pid -ne $PID){ Stop-Process -Id $pid -Force } }`,
  ], { cwd: repoRoot, env: { ...process.env } }, logPath)
}

async function cleanupChildProcess(child, logPath) {
  if (!child || child.killed) return
  if (process.platform === 'win32' && child.pid) {
    await runBestEffort('taskkill.exe', ['/PID', String(child.pid), '/F', '/T'], { cwd: repoRoot, env: { ...process.env } }, logPath)
    return
  }
  child.kill('SIGTERM')
}
'''
if 'async function freePort(port, logPath)' not in s:
    s = s.replace(insert_after, insert_after + helper)

s = s.replace(
    "  try {\n    await runCommand(npmBin, ['run', 'build'], { cwd: frontendDir, env: { ...process.env, VITE_REZZERV_VERSION: version } }, frontendLogPath)",
    "  try {\n    await freePort(frontendPort, frontendLogPath)\n    await freePort(backendPort, backendLogPath)\n    await runCommand(npmBin, ['run', 'build'], { cwd: frontendDir, env: { ...process.env, VITE_REZZERV_VERSION: version } }, frontendLogPath)",
)

s = s.replace(
    "    if (frontendProcess && !frontendProcess.killed) frontendProcess.kill('SIGTERM')\n    if (backendProcess && !backendProcess.killed) backendProcess.kill('SIGTERM')",
    "    await cleanupChildProcess(frontendProcess, frontendLogPath)\n    await cleanupChildProcess(backendProcess, backendLogPath)\n    await freePort(frontendPort, frontendLogPath)\n    await freePort(backendPort, backendLogPath)",
)

s = s.replace(
    "    await page.waitForSelector('[data-testid=\"regression-runner-page\"]', { timeout: 60000 })",
    "    await page.waitForSelector('[data-testid=\"regression-runner-page\"]', { timeout: 60000 }).catch((error) => { throw new Error(`frontend_unreachable: ${page.url()} — ${error.message}`) })",
)

path.write_text(s, encoding='utf-8')
print('R7c-26 regression runner lifecycle patch applied')
