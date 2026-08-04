import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const projectRoot = path.resolve(process.cwd())
const panelSource = fs.readFileSync(
  path.join(projectRoot, 'src/features/purchaseImport/DayArticleHandlingPanel.jsx'),
  'utf8',
)
const wrapperSource = fs.readFileSync(
  path.join(projectRoot, 'src/features/purchaseImport/StoreBatchDetailPage.jsx'),
  'utf8',
)

describe('Release B2 koppeling met Uitpakken', () => {
  it('plaatst het B2-paneel in de bestaande Uitpakken-integratielaag', () => {
    expect(wrapperSource).toContain('BaseStoreBatchDetailContent')
    expect(wrapperSource).toContain('<DayArticleHandlingPanel batchId={batchId} />')
    expect(wrapperSource).toContain('data-testid="uitpakken-b2-content"')
  })

  it('leest alleen gekoppelde huishoudartikelen via de batch-API', () => {
    expect(panelSource).toContain('matched_household_article_id')
    expect(panelSource).toContain('fetchInventoryHandlingByArticleIds')
    expect(panelSource).toContain('rows.filter((row) => row.linked)')
  })

  it('toont de B2-kolommen zonder de verwerkingsmutatie te wijzigen', () => {
    expect(panelSource).toContain('<th>Standaardverwerking</th>')
    expect(panelSource).toContain('<th>Locatie</th>')
    expect(panelSource).toContain('<th>Sublocatie</th>')
    expect(panelSource).toContain("row.location || 'Bestaande keuze'")
    expect(panelSource).toContain("row.sublocation || 'Bestaande keuze'")
    expect(panelSource).not.toContain('/direct-consumption')
  })
})
