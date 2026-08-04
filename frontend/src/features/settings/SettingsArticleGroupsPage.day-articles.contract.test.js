import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const projectRoot = path.resolve(process.cwd())
const source = fs.readFileSync(
  path.join(projectRoot, 'src/features/settings/SettingsArticleGroupsPage.jsx'),
  'utf8',
)
const routerSource = fs.readFileSync(
  path.join(projectRoot, 'src/app/router/AppRouter.jsx'),
  'utf8',
)

describe('Release B1 native Tabellen', () => {
  it('routeert rechtstreeks naar SettingsArticleGroupsPage', () => {
    expect(routerSource).toContain("SettingsArticleGroupsPage from '../../features/settings/SettingsArticleGroupsPage'")
    expect(routerSource).not.toContain('SettingsArticleGroupsWithInventoryHandling')
  })

  it('rendert Standaardverwerking rechtstreeks in beide Table-componenten', () => {
    expect((source.match(/<Table/g) || []).length).toBe(2)
    expect((source.match(/Standaardverwerking/g) || []).length).toBeGreaterThanOrEqual(2)
    expect(source).toContain('columnKey="handling"')
    expect(source).toContain('colSpan={4}')
  })

  it('gebruikt geen portal of DOM-injectie', () => {
    expect(source).not.toContain('createPortal')
    expect(source).not.toContain('MutationObserver')
    expect(source).not.toContain('document.querySelector')
    expect(source).not.toContain('appendChild')
  })

  it('behoudt de eenrichtingswerking van groep naar artikelen', () => {
    expect(source).toContain('setGroupHandling')
    expect(source).toContain('setArticleHandling')
    expect(source).toContain('groupArticles')
    expect(source).not.toContain('setGroupHandling(article')
  })

  it('toont in beide eerste kolomkoppen een selecteer-alles-checkbox zonder teksttitel', () => {
    expect(source).toContain('toggleAllVisibleGroups')
    expect(source).toContain('toggleAllVisibleArticles')
    expect(source).toContain('Selecteer alle zichtbare selecteerbare Artikelgroepen')
    expect(source).toContain('Selecteer alle zichtbare huishoudartikelen')
    expect(source).not.toContain('>Selectie</ResizableHeaderCell>')
  })
})
