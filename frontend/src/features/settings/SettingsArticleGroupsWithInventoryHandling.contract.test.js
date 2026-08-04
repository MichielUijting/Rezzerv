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

  it('gebruikt huishoudartikelen en voegt de kolom aan beide tabellen toe', () => {
    expect(source).toContain('/api/article-groups/household-articles')
    expect(source).toContain('Standaardverwerking')
    expect(source).toContain('GroupHandlingCell')
    expect(source).toContain('ArticleHandlingCell')
  })

  it('gebruikt checkboxes waarbij aangevinkt direct consumeren betekent', () => {
    expect(source).toContain("checked ? DIRECT_CONSUMPTION : STOCK")
    expect(source).toContain("type=\"checkbox\"")
    expect(source).toContain("title={checked ? 'Direct consumeren' : 'Opslaan in voorraad'}")
  })

  it('past de groepskeuze een richting op alle gekoppelde artikelen toe', () => {
    expect(source).toContain('for (const article of articles)')
    expect(source).toContain('saveHandling(householdId, article.id, nextChecked)')
    expect(source).toContain('onSavedMany')
    expect(source).not.toContain('setChecked(value === DIRECT_CONSUMPTION)')
  })

  it('houdt beide tabellen binnen dezelfde vaste breedte zonder extra horizontale kolomgroei', () => {
    expect(source).toContain('const GROUP_COLUMN_WIDTHS = [48, 330, 210, 180]')
    expect(source).toContain('const ARTICLE_COLUMN_WIDTHS = [48, 300, 240, 180]')
    expect(source).toContain("table.style.maxWidth = '100%'")
    expect(source).not.toContain('parsedWidth + COLUMN_WIDTH')
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