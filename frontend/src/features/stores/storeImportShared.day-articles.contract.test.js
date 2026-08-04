import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const projectRoot = path.resolve(process.cwd())
const sharedSource = fs.readFileSync(
  path.join(projectRoot, 'src/features/stores/storeImportShared.jsx'),
  'utf8',
)
const integrationSource = fs.readFileSync(
  path.join(projectRoot, 'src/features/purchaseImport/StoreBatchDetailPage.jsx'),
  'utf8',
)

describe('Release B2 native Uitpakken-locatie', () => {
  it('gebruikt geen losse B2-tabel of paneel meer', () => {
    expect(integrationSource).toBe("export { default, StoreBatchDetailContent } from '../stores/StoreBatchDetailPage';")
    expect(integrationSource).not.toContain('DayArticleHandlingPanel')
  })

  it('leest artikelstandaarden voor de bestaande purchase-import-batch', () => {
    expect(sharedSource).toContain('addDayArticlePresentation')
    expect(sharedSource).toContain('/articles/inventory-handling/batch')
    expect(sharedSource).toContain('matched_household_article_id')
  })

  it('zet een dagartikel op de beschermde Direct-locatie in de bestaande regel', () => {
    expect(sharedSource).toContain("const DIRECT_CONSUMPTION = 'DIRECT_CONSUMPTION'")
    expect(sharedSource).toContain("default_inventory_handling_label: 'Direct consumeren'")
    expect(sharedSource).toContain('target_location_id: protectedDirectLocationId')
    expect(sharedSource).toContain('suggested_location_id: protectedDirectLocationId')
    expect(sharedSource).toContain('/purchase-import-lines/inventory-handling-overrides/batch')
    expect(sharedSource).toContain('const effectiveHandling = lineOverride || articleDefault')
  })

  it('laat de bestaande Uitpakken-flow bruikbaar bij een aanvullende lookupfout', () => {
    expect(sharedSource).toContain('return batch')
    expect(sharedSource).not.toContain('/direct-consumption')
  })
})
