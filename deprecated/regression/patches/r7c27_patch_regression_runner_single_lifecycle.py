from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'frontend' / 'scripts' / 'run-regression.mjs'
s = path.read_text(encoding='utf-8')

# Dynamic, non-conflicting default ports.
s = s.replace(
    'const frontendPort = Number(process.env.REZZERV_FRONTEND_PORT || 5174)\nconst backendPort = Number(process.env.REZZERV_BACKEND_PORT || 8001)',
    'const dynamicPortOffset = 2000 + Math.floor(Math.random() * 3000)\nconst frontendPort = Number(process.env.REZZERV_FRONTEND_PORT || (15000 + dynamicPortOffset))\nconst backendPort = Number(process.env.REZZERV_BACKEND_PORT || (18000 + dynamicPortOffset))',
)

# Do not use npm.cmd for internal runner orchestration; run Vite through Node directly.
s = s.replace(
    "const npmBin = process.platform === 'win32' ? 'npm.cmd' : 'npm'",
    "const npmBin = process.platform === 'win32' ? 'npm.cmd' : 'npm'\nconst viteBin = path.join(frontendDir, 'node_modules', 'vite', 'bin', 'vite.js')",
)

# Remove fragile Windows cmd.exe wrapping for internal commands.
start = s.find('function windowsQuote(value) {')
end = s.find('\n\nfunction spawnLogged', start)
if start >= 0 and end >= 0:
    s = s[:start] + "function normalizeSpawn(command, args = []) {\n  return { command, args, shell: false }\n}" + s[end:]

# Replace python -c probe with a probe file.
old_probe = "try { await runCommand(venvPython, ['-c', 'import fastapi; import sqlalchemy; import uvicorn'], { cwd: backendDir, env: { ...process.env } }, installLogPath); ready = true } catch { ready = false }"
new_probe = "const probePath = path.join(reportDir, `backend-python-probe-${timestamp}.py`)\n  await fsp.writeFile(probePath, 'import fastapi\\nimport sqlalchemy\\nimport uvicorn\\n', 'utf8')\n  try { await runCommand(venvPython, [probePath], { cwd: backendDir, env: { ...process.env } }, installLogPath); ready = true } catch { ready = false }"
s = s.replace(old_probe, new_probe)

# Correct Playwright argument order.
s = s.replace('}, { timeout: 300000 })', '}, undefined, { timeout: 300000 })')

# Add tracked-PID cleanup helpers, no PowerShell/netstat parsing.
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

async function cleanupChildProcess(child, logPath) {
  if (!child || child.killed) return
  if (process.platform === 'win32' && child.pid) {
    await runBestEffort('taskkill.exe', ['/PID', String(child.pid), '/F', '/T'], { cwd: repoRoot, env: { ...process.env } }, logPath)
    return
  }
  child.kill('SIGTERM')
}
'''
if 'async function cleanupChildProcess(child, logPath)' not in s:
    s = s.replace(insert_after, insert_after + helper)

# Use Node/Vite directly for build and dev: exactly one frontend child process.
s = s.replace(
    "await runCommand(npmBin, ['run', 'build'], { cwd: frontendDir, env: { ...process.env, VITE_REZZERV_VERSION: version } }, frontendLogPath)",
    "await runCommand(process.execPath, [viteBin, 'build'], { cwd: frontendDir, env: { ...process.env, VITE_REZZERV_VERSION: version } }, frontendLogPath)",
)
s = s.replace(
    "frontendProcess = spawnLogged(npmBin, ['run', 'dev', '--', '--host', '127.0.0.1', '--port', String(frontendPort)], { cwd: frontendDir, env: { ...process.env, VITE_REZZERV_VERSION: version } }, frontendLogPath)",
    "frontendProcess = spawnLogged(process.execPath, [viteBin, '--host', '127.0.0.1', '--port', String(frontendPort)], { cwd: frontendDir, env: { ...process.env, VITE_REZZERV_VERSION: version } }, frontendLogPath)",
)

# Fail fast if the regression page shell is not present.
s = s.replace(
    "await page.waitForSelector('[data-testid=\"regression-runner-page\"]', { timeout: 60000 })",
    "await page.waitForSelector('[data-testid=\"regression-runner-page\"]', { timeout: 60000 }).catch((error) => { throw new Error(`frontend_unreachable: ${page.url()} — ${error.message}`) })",
)

# Controlled teardown using tracked PIDs only.
s = s.replace(
    "if (frontendProcess && !frontendProcess.killed) frontendProcess.kill('SIGTERM')\n    if (backendProcess && !backendProcess.killed) backendProcess.kill('SIGTERM')",
    "await cleanupChildProcess(frontendProcess, frontendLogPath)\n    await cleanupChildProcess(backendProcess, backendLogPath)",
)

path.write_text(s, encoding='utf-8')
print('R7c-27 single lifecycle regression runner patch applied')
