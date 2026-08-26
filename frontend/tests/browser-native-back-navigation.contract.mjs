import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const testDir = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(testDir, '..')
const sourceRoot = path.join(frontendRoot, 'src')
const sourceExtensions = new Set(['.js', '.jsx', '.ts', '.tsx'])

const allowedLocalStateBackLabels = new Set([
  'Terug naar overzicht',
  'Terug naar scherm',
])

const forbiddenHistoryPatterns = [
  { label: 'navigate(-1)', pattern: /\bnavigate\s*\(\s*-1\s*\)/g },
  { label: 'history.back()', pattern: /\b(?:window\.)?history\.back\s*\(/g },
  { label: 'history.go(-1)', pattern: /\b(?:window\.)?history\.go\s*\(\s*-1\s*\)/g },
]

function listSourceFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const entryPath = path.join(directory, entry.name)
    if (entry.isDirectory()) return listSourceFiles(entryPath)
    return sourceExtensions.has(path.extname(entry.name).toLowerCase()) ? [entryPath] : []
  })
}

function lineNumberAt(content, index) {
  return content.slice(0, index).split('\n').length
}

function normalizeBackLabel(rawLabel) {
  return String(rawLabel || '')
    .replace(/^←\s*/, '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[.,;:!?]+$/, '')
}

const violations = []

for (const filePath of listSourceFiles(sourceRoot)) {
  const relativePath = path.relative(frontendRoot, filePath).replaceAll('\\', '/')
  const content = fs.readFileSync(filePath, 'utf8')

  for (const { label, pattern } of forbiddenHistoryPatterns) {
    pattern.lastIndex = 0
    for (const match of content.matchAll(pattern)) {
      violations.push(`${relativePath}:${lineNumberAt(content, match.index)} gebruikt ${label}; gebruik browsernavigatie.`)
    }
  }

  const backLabelPattern = /(?:←\s*)?Terug naar [^<>{}\n'"`]+/g
  for (const match of content.matchAll(backLabelPattern)) {
    const normalized = normalizeBackLabel(match[0])
    if (allowedLocalStateBackLabels.has(normalized)) continue
    violations.push(`${relativePath}:${lineNumberAt(content, match.index)} bevat ongewenste terugnavigatie: “${normalized}”.`)
  }
}

if (violations.length) {
  console.error('Browser-native back-navigation contract FAILED:')
  violations.forEach((violation) => console.error(`- ${violation}`))
  process.exit(1)
}

console.log('BROWSER_NATIVE_BACK_NAVIGATION_CONTRACT_GREEN')
