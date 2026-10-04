import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  MIN_RESIZABLE_COLUMN_WIDTH,
  resizeTableBoundary,
  tableWidthTotal,
} from '../src/ui/tableResize.js'

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

function assertEqual(actual, expected, message) {
  assert(actual === expected, `${message} (verwacht ${expected}, kreeg ${actual})`)
}

function verifyResizeInvariant(startWidths, boundaryIndex, delta, label) {
  const resized = resizeTableBoundary(startWidths, boundaryIndex, delta)
  assertEqual(
    tableWidthTotal(resized),
    tableWidthTotal(startWidths),
    `${label}: totale tabelbreedte veranderde`,
  )
  return resized
}

const growMiddle = verifyResizeInvariant([48, 420, 140], 1, 60, 'middelste kolom breder')
assertEqual(growMiddle[0], 48, 'selectiekolom mag niet verschuiven')
assertEqual(growMiddle[1], 480, 'linkerkolom moet 60px breder worden')
assertEqual(growMiddle[2], 80, 'rechter buurkollom moet 60px smaller worden')

const shrinkMiddle = verifyResizeInvariant([48, 420, 140], 1, -80, 'middelste kolom smaller')
assertEqual(shrinkMiddle[1], 340, 'linkerkolom moet 80px smaller worden')
assertEqual(shrinkMiddle[2], 220, 'rechter buurkolom moet 80px breder worden')

const clampRight = verifyResizeInvariant([48, 420, 80], 1, 200, 'rechter minimumgrens')
assertEqual(clampRight[2], MIN_RESIZABLE_COLUMN_WIDTH, 'rechter kolom moet op minimum stoppen')
assertEqual(clampRight[1], 444, 'alleen beschikbare breedte mag naar linkerkolom gaan')

const narrowSelection = verifyResizeInvariant([48, 420, 140], 0, -100, 'bestaande smalle selectiekolom')
assertEqual(narrowSelection[0], 48, 'bestaande 48px-selectiekolom mag niet naar 56px springen')
assertEqual(narrowSelection[1], 420, 'buurkolom mag bij geblokkeerde versmalling niet wijzigen')

const invalidBoundary = resizeTableBoundary([48, 420, 140], 2, 50)
assertEqual(tableWidthTotal(invalidBoundary), 608, 'buitenste rechterrand mag tabelbreedte niet wijzigen')
assertEqual(invalidBoundary.join(','), '48,420,140', 'buitenste rechterrand mag geen kolom wijzigen')

const testDir = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(testDir, '..')
const sourceRoot = path.join(frontendRoot, 'src')
const sourceExtensions = new Set(['.js', '.jsx', '.ts', '.tsx'])
const sharedResizeFiles = new Set([
  'src/ui/Table.jsx',
  'src/ui/resizableTable.jsx',
  'src/ui/tableResize.js',
])
const lowLevelResizePatterns = [
  { label: 'resize-handle markup', pattern: /rz-column-resize-handle/g },
  { label: 'resize body-state', pattern: /rz-table-column-resizing/g },
  { label: 'fixed-width resize primitive', pattern: /resizeTableBoundary/g },
  { label: 'resize minimum constant', pattern: /MIN_RESIZABLE_COLUMN_WIDTH/g },
  { label: 'custom column-resize cursor', pattern: /col-resize/g },
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

const violations = []
for (const filePath of listSourceFiles(sourceRoot)) {
  const relativePath = path.relative(frontendRoot, filePath).replaceAll('\\', '/')
  if (sharedResizeFiles.has(relativePath)) continue

  const content = fs.readFileSync(filePath, 'utf8')
  for (const { label, pattern } of lowLevelResizePatterns) {
    pattern.lastIndex = 0
    for (const match of content.matchAll(pattern)) {
      violations.push(
        `${relativePath}:${lineNumberAt(content, match.index)} bevat eigen ${label}; gebruik het gedeelde Table/DataTable-resizefundament.`,
      )
    }
  }
}

if (violations.length) {
  console.error('FIXED_TABLE_WIDTH_CONTRACT_FAILED')
  violations.forEach((violation) => console.error(`- ${violation}`))
  process.exit(1)
}

console.log('FIXED_TABLE_WIDTH_CONTRACT_GREEN')
