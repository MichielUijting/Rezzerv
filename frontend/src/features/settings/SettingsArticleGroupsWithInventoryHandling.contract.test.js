import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const projectRoot = path.resolve(process.cwd())
const source = fs.readFileSync(
  path.join(projectRoot, 'src/features/settings/SettingsArticleGroupsWithInventoryHandling.jsx'),
  'utf8',
)
const routerSource = fs.readFileSync(
  path.join(projectRoot, 'src/app/router/AppRouter.jsx'),
  'utf8',
)

describe('Release B1 in Beheer Artikelgroepen', () => {
  it('routeert alleen Artikelgroepen via de B1-integratie en laat Voorraad ongemoeid', () => {
    expect(routerSource).toContain("SettingsArticleGroupsWithInventoryHandling.jsx")
    expect(routerSource).toContain("import ArticlePage from '../../features/articles/ArticlePage'")
    expect(routerSource).not.toContain('ArticlePageWithInventoryHandling')
  })

  it('gebruikt household_articles en voegt Standaardverwerking toe', () => {
    expect(source).toContain('/api/article-groups/household-articles')
    expect(source).toContain('Standaardverwerking')
    expect(source).toContain('Opslaan in voorraad')
    expect(source).toContain('Direct consumeren')
  })

  it('wijzigt de permanente standaard alleen met beheerrecht', () => {
    expect(source).toContain("permissions['articles.manage'] === true")
    expect(source).toContain("displayRole === 'admin'")
    expect(source).toContain("canonicalRole === 'owner'")
    expect(source).not.toContain("displayRole === 'lid'")
  })

  it('corrigeert de misleidende voorraadterminologie', () => {
    expect(source).toContain('Huishoudartikelen laden…')
    expect(source).toContain('Geen huishoudartikelen gevonden.')
    expect(source).toContain('Geen huishoudartikelen voor deze selectie.')
  })
})
