import { describe, expect, it } from 'vitest'
import {
  normalizeHouseholdArticleOption,
  normalizeHouseholdArticleOptionsPayload,
  shouldNormalizeHouseholdArticleOptions,
} from './householdArticleOptionAdapter.js'

describe('Uitpakken huishoudartikelopties', () => {
  it('gebruikt voor een bestaand artikel altijd de echte household_article_id', () => {
    expect(normalizeHouseholdArticleOption({
      id: 'article::Appel',
      household_article_id: 'uuid-appel',
      article_name: 'Appel',
    })).toMatchObject({
      id: 'uuid-appel',
      household_article_id: 'uuid-appel',
      name: 'Appel',
    })
  })

  it('behoudt voor een nieuw artikel de reeds teruggegeven huishoudartikel-id', () => {
    expect(normalizeHouseholdArticleOption({ id: 'uuid-nieuw', name: 'Nieuw artikel' })).toMatchObject({
      id: 'uuid-nieuw',
      household_article_id: 'uuid-nieuw',
      name: 'Nieuw artikel',
    })
  })

  it('dedupliceert opties op household_article_id', () => {
    const normalized = normalizeHouseholdArticleOptionsPayload([
      { id: 'article::Appel', household_article_id: 'uuid-appel', article_name: 'Appel' },
      { id: 'uuid-appel', name: 'Appel' },
    ])
    expect(normalized).toHaveLength(1)
    expect(normalized[0].id).toBe('uuid-appel')
  })

  it('past de normalisatie alleen toe op de bestaande review-artikelenroute', () => {
    expect(shouldNormalizeHouseholdArticleOptions('/api/store-review-articles')).toBe(true)
    expect(shouldNormalizeHouseholdArticleOptions('/api/store-review-articles?x=1')).toBe(true)
    expect(shouldNormalizeHouseholdArticleOptions('/api/purchase-import-batches/1')).toBe(false)
  })
})
