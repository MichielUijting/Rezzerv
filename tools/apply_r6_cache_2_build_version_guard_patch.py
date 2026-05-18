from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / 'frontend' / 'Dockerfile'
VERSION_JS = ROOT / 'frontend' / 'src' / 'ui' / 'version.js'
APP_JSX = ROOT / 'frontend' / 'src' / 'App.jsx'
BUILD_INFO = ROOT / 'frontend' / 'src' / 'ui' / 'buildInfo.js'

for target in [DOCKERFILE, VERSION_JS, APP_JSX, BUILD_INFO]:
    if target.exists():
        target.with_suffix(target.suffix + '.bak-r6-cache-2').write_text(target.read_text(encoding='utf-8-sig'), encoding='utf-8')

# 1) Ensure a build-info module exists for dev/local source runs.
if not BUILD_INFO.exists():
    BUILD_INFO.write_text("export const REZZERV_BUILD_ID = 'dev-source'\n", encoding='utf-8')

# 2) Docker build writes a unique build id into both source module and version.json before Vite builds.
docker_content = DOCKERFILE.read_text(encoding='utf-8-sig')
old_docker = """COPY . .
RUN node ./node_modules/vite/bin/vite.js build
"""
new_docker = """COPY . .
RUN node -e \"const fs=require('fs'); const id=String(Date.now())+'-'+Math.random().toString(36).slice(2,10); const version=process.env.VITE_REZZERV_VERSION||'dev'; fs.writeFileSync('src/ui/buildInfo.js', 'export const REZZERV_BUILD_ID = '+JSON.stringify(id)+'\\n'); fs.mkdirSync('public',{recursive:true}); fs.writeFileSync('public/version.json', JSON.stringify({version, buildId:id})+'\\n');\"
RUN node ./node_modules/vite/bin/vite.js build
"""
if new_docker not in docker_content:
    if old_docker not in docker_content:
        raise SystemExit('R6-cache-2 aborted: Dockerfile build anchor not found.')
    docker_content = docker_content.replace(old_docker, new_docker, 1)
DOCKERFILE.write_text(docker_content, encoding='utf-8')

# 3) Version utility exposes current build id and active server version fetch.
version_content = VERSION_JS.read_text(encoding='utf-8-sig')
if "import { REZZERV_BUILD_ID } from './buildInfo.js'" not in version_content:
    version_content = "import { REZZERV_BUILD_ID } from './buildInfo.js'\n" + version_content

if 'export function getRezzervBuildId()' not in version_content:
    version_content += """

export function getRezzervBuildId() {
  return normalizeVersion(REZZERV_BUILD_ID) || 'dev-source'
}

export async function fetchServedRezzervVersionInfo() {
  const response = await fetch(`/version.json?ts=${Date.now()}`, { cache: 'no-store' })
  if (!response.ok) return null
  return response.json()
}

export function reloadForFreshFrontendBuild(serverBuildId) {
  if (typeof window === 'undefined') return
  const normalizedServerBuildId = normalizeVersion(serverBuildId)
  const url = new URL(window.location.href)
  url.searchParams.set('_rz_build', normalizedServerBuildId || String(Date.now()))
  window.location.replace(url.toString())
}
"""
VERSION_JS.write_text(version_content, encoding='utf-8')

# 4) App actively checks build freshness and reloads stale bundles.
app_content = APP_JSX.read_text(encoding='utf-8-sig')
old_import = "import { getRezzervVersionTag } from \"./ui/version\";"
new_import = "import { fetchServedRezzervVersionInfo, getRezzervBuildId, getRezzervVersionTag, reloadForFreshFrontendBuild } from \"./ui/version\";"
if new_import not in app_content:
    if old_import not in app_content:
        raise SystemExit('R6-cache-2 aborted: App version import anchor not found.')
    app_content = app_content.replace(old_import, new_import, 1)

old_effect = """  useEffect(() => {
    const refreshVersion = () => setBuildTag(getRezzervVersionTag());
    window.addEventListener(\"rezzerv-version-ready\", refreshVersion);
    return () => window.removeEventListener(\"rezzerv-version-ready\", refreshVersion);
  }, []);
"""
new_effect = """  useEffect(() => {
    const refreshVersion = () => setBuildTag(getRezzervVersionTag());
    window.addEventListener(\"rezzerv-version-ready\", refreshVersion);
    return () => window.removeEventListener(\"rezzerv-version-ready\", refreshVersion);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const currentBuildId = getRezzervBuildId();
    const checkBuildFreshness = async () => {
      try {
        const served = await fetchServedRezzervVersionInfo();
        if (cancelled || !served?.buildId) return;
        if (String(served.buildId) !== String(currentBuildId)) {
          reloadForFreshFrontendBuild(served.buildId);
        }
      } catch {
        // ignore version check errors; normal app/API error handling remains responsible
      }
    };
    checkBuildFreshness();
    const intervalId = window.setInterval(checkBuildFreshness, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);
"""
if 'fetchServedRezzervVersionInfo' in app_content and 'reloadForFreshFrontendBuild' in app_content and 'setInterval(checkBuildFreshness' not in app_content:
    if old_effect not in app_content:
        raise SystemExit('R6-cache-2 aborted: App useEffect anchor not found.')
    app_content = app_content.replace(old_effect, new_effect, 1)
elif 'setInterval(checkBuildFreshness' not in app_content:
    if old_effect not in app_content:
        raise SystemExit('R6-cache-2 aborted: App useEffect anchor not found.')
    app_content = app_content.replace(old_effect, new_effect, 1)
APP_JSX.write_text(app_content, encoding='utf-8')

# Guard checks.
for target, markers in {
    DOCKERFILE: ['buildId', 'src/ui/buildInfo.js', 'public/version.json'],
    VERSION_JS: ['REZZERV_BUILD_ID', 'fetchServedRezzervVersionInfo', 'reloadForFreshFrontendBuild'],
    APP_JSX: ['checkBuildFreshness', 'setInterval(checkBuildFreshness', 'reloadForFreshFrontendBuild'],
    BUILD_INFO: ['REZZERV_BUILD_ID'],
}.items():
    content = target.read_text(encoding='utf-8')
    for marker in markers:
        if marker not in content:
            raise SystemExit(f'R6-cache-2 guard failed: {marker!r} missing in {target}')

print('R6-cache-2 build version guard patch applied')
print('Updated:', DOCKERFILE)
print('Updated:', VERSION_JS)
print('Updated:', APP_JSX)
print('Ensured:', BUILD_INFO)
