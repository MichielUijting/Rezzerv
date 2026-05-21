from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'frontend' / 'scripts' / 'run-regression.mjs'
s = path.read_text(encoding='utf-8')

s = s.replace(
    'const frontendPort = Number(process.env.REZZERV_FRONTEND_PORT || 5174)\nconst backendPort = Number(process.env.REZZERV_BACKEND_PORT || 8001)',
    'const dynamicPortOffset = 2000 + Math.floor(Math.random() * 3000)\nconst frontendPort = Number(process.env.REZZERV_FRONTEND_PORT || (15000 + dynamicPortOffset))\nconst backendPort = Number(process.env.REZZERV_BACKEND_PORT || (18000 + dynamicPortOffset))',
)

start = s.find('function windowsQuote(value) {')
end = s.find('\n\nfunction spawnLogged', start)
if start < 0 or end < 0:
    raise SystemExit('spawn normalization block not found')
s = s[:start] + "function normalizeSpawn(command, args = []) {\n  return { command, args, shell: false }\n}" + s[end:]

old_probe = "try { await runCommand(venvPython, ['-c', 'import fastapi; import sqlalchemy; import uvicorn'], { cwd: backendDir, env: { ...process.env } }, installLogPath); ready = true } catch { ready = false }"
new_probe = "const probePath = path.join(reportDir, `backend-python-probe-${timestamp}.py`)\n  await fsp.writeFile(probePath, 'import fastapi\\nimport sqlalchemy\\nimport uvicorn\\n', 'utf8')\n  try { await runCommand(venvPython, [probePath], { cwd: backendDir, env: { ...process.env } }, installLogPath); ready = true } catch { ready = false }"
s = s.replace(old_probe, new_probe)

s = s.replace('}, { timeout: 300000 })', '}, undefined, { timeout: 300000 })')

path.write_text(s, encoding='utf-8')
print('R7c-25 regression runner patch applied')
