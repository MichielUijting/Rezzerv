import demoData from '../../demo-articles.json'
import { getHouseholdAutomationSettings } from '../settings/services/householdAutomationService'
import { AUTO_CONSUME_MODES, getArticleAutoConsumeMode } from '../articles/services/articleAutomationOverrideService'

function isConsumableArticle(option) {
  if (!option) return false
  if (option.consumable === true) return true
  const type = option.type || option.article_type || ''
  return type === 'Voedsel & drank' || type === 'Huishoudelijk'
}

function buildConsumableLookup() {
  const lookup = new Map()
  for (const article of demoData?.articles || []) {
    lookup.set(String(article.id), isConsumableArticle(article))
  }
  return lookup
}

const CONSUMABLE_LOOKUP = buildConsumableLookup()

export function buildAutoConsumeArticleIds(lines = []) {
  const settings = getHouseholdAutomationSettings()
  const articleIds = new Set()

  for (const line of lines) {
    const articleId = String(line?.matched_household_article_id || '')
    if (!articleId) continue
    if (!CONSUMABLE_LOOKUP.get(articleId)) continue
    const overrideMode = getArticleAutoConsumeMode(articleId)
    if (overrideMode === AUTO_CONSUME_MODES.ALWAYS_ON) {
      articleIds.add(articleId)
      continue
    }
    if (overrideMode === AUTO_CONSUME_MODES.ALWAYS_OFF) {
      continue
    }
    if (settings.autoConsumeOnRepurchase) {
      articleIds.add(articleId)
    }
  }

  return Array.from(articleIds)
}
