from pathlib import Path

p = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'features' / 'admin' / 'RegressionRunnerPage.jsx'
s = p.read_text(encoding='utf-8')

s = s.replace('const RUNNER_TIMEOUT_MS = 240000', 'const RUNNER_TIMEOUT_MS = 180000')
s = s.replace('    if (hasStartedRef.current) return undefined\n    hasStartedRef.current = true\n    let cancelled = false\n', '    if (hasStartedRef.current) return () => {}\n    hasStartedRef.current = true\n    let cancelled = false\n')
s = s.replace('    return () => { cancelled = true }\n', '    return () => {\n      cancelled = true\n      hasStartedRef.current = false\n    }\n')

p.write_text(s, encoding='utf-8')
print('R7c-28 regression runner status lifecycle patch applied')
