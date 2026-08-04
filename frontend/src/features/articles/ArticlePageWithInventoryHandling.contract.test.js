import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const projectRoot = path.resolve(process.cwd())
const wrapperSource = fs.readFileSync(
  path.join(projectRoot, 'src/features/articles/ArticlePageWithInventoryHandling.jsx'),
  'utf8',
)
const routerSource = fs.readFileSync(
  path.join(projectRoot, 'src/app/router/AppRouter.jsx'),
  'utf8',
)

describe('Release B1 artikelstandaard integratie', () => {
  it('routeert de artikelpagina via de B1-wrapper', () => {
    expect(routerSource).toContain("ArticlePageWithInventoryHandling.jsx")
    expect(routerSource).toContain("path: '/voorraad/:articleId'")
  })

  it('plaatst het veld in de bestaande huishoudinstellingenkaart', () => {
    expect(wrapperSource).toContain('article-household-settings-section')
    expect(wrapperSource).toContain('rz-overview-group-body')
    expect(wrapperSource).toContain('<InventoryHandlingField')
  })

  it('geeft alleen beheerder/eigenaar of articles.manage schrijfrecht', () => {
    expect(wrapperSource).toContain("permissions['articles.manage'] === true")
    expect(wrapperSource).toContain("displayRole === 'admin'")
    expect(wrapperSource).toContain("canonicalRole === 'owner'")
    expect(wrapperSource).not.toContain("displayRole === 'lid'")
  })
})
