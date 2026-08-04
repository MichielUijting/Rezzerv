import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const sourcePath = path.join(here, 'InventoryHandlingOverrideSelect.jsx')
const source = fs.readFileSync(sourcePath, 'utf8')

function expectSource(fragment, message) {
  if (!source.includes(fragment)) throw new Error(message)
}

expectSource('Standaard: {inventoryHandlingLabel(articleDefault)}', 'B3 selector must expose the article default')
expectSource('<option value={STOCK}>Opslaan in voorraad</option>', 'B3 selector must offer STOCK override')
expectSource('<option value={DIRECT_CONSUMPTION}>Direct consumeren</option>', 'B3 selector must offer DIRECT_CONSUMPTION override')
expectSource('normalizeInventoryHandlingOverride(event.target.value)', 'B3 selector must normalize persisted values')
expectSource('effectiveInventoryHandling(articleDefault, normalizedOverride)', 'B3 selector must use the central effective-handling rule')
expectSource('onChange?.(nextValue)', 'B3 selector must emit the temporary line override')

console.log('PASS B3 inventory handling override selector contract')
