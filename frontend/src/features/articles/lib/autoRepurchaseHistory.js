import { getHouseholdAutomationSettings } from '../../settings/services/householdAutomationService'
import { AUTO_CONSUME_MODES, getArticleAutoConsumeMode } from '../services/articleAutomationOverrideService'

function isConsumable(article = {}) {
  if (article.consumable === true) return true
  return article.type === 'Voedsel & drank' || article.type === 'Huishoudelijk'
}

function toNumber(value) {
  const num = Number(value)
  return Number.isFinite(num) ? num : 0
}

function shiftTimeOneMinuteBack(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  date.setMinutes(date.getMinutes() - 1)
  return date.toISOString()
}

function shouldApplyAutoRepurchase(article = {}, settings = {}) {
  if (!isConsumable(article)) return false

  const overrideMode = getArticleAutoConsumeMode(article.id)
  if (overrideMode === AUTO_CONSUME_MODES.ALWAYS_ON) return true
  if (overrideMode === AUTO_CONSUME_MODES.ALWAYS_OFF) return false

  return Boolean(settings.autoConsumeOnRepurchase)
}

export function applyAutoRepurchaseHistory(article = {}) {
  const settings = getHouseholdAutomationSettings()
  const history = Array.isArray(article.history) ? article.history : []

  if (!shouldApplyAutoRepurchase(article, settings) || !history.length) {
    return history
  }

  const hasRealAutoRepurchaseEvent = history.some(
    (entry) => entry?.event_type === 'auto_repurchase' || entry?.source === 'auto_repurchase',
  )
  if (hasRealAutoRepurchaseEvent) {
    return history
  }

  const sorted = [...history].sort((a, b) => new Date(a.datetime || 0) - new Date(b.datetime || 0))
  const enriched = []

  sorted.forEach((entry) => {
    const isPurchase = entry?.type === 'Aankoop'
    const previousStock = toNumber(entry?.old_value)
    const alreadyAutoRepurchase = entry?.source === 'auto_repurchase' || entry?.auto_generated === true
    const purchaseQuantity = toNumber(entry?.quantity_change || Math.max(0, toNumber(entry?.new_value) - previousStock))
    const qualifies = isPurchase && !alreadyAutoRepurchase && previousStock > 0 && purchaseQuantity > 0

    if (!qualifies) {
      enriched.push(entry)
      return
    }

    enriched.push({
      datetime: shiftTimeOneMinuteBack(entry.datetime),
      type: 'Verbruik',
      old_value: String(previousStock),
      new_value: '0',
      location: entry.location || 'Onbekende locatie',
      source: 'auto_repurchase',
      note: 'Automatisch afgeboekt bij herhaalaankoop volgens huishoudinstelling.',
      quantity_change: previousStock,
      auto_generated: true,
    })

    enriched.push({
      ...entry,
      old_value: '0',
      new_value: String(purchaseQuantity),
      note: `${entry.note || ''}${entry.note ? ' ' : ''}Aankoop geregistreerd na automatische afboeking.`.trim(),
    })
  })

  return enriched
}
