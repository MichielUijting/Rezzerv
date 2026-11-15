/**
 * Process-only projection of server-authoritative Artikelbeheer read models.
 * Never matches by name, assigns a Catalogus ID, or grants write permissions.
 * A row is one unresolved source identity or one (product, classification system).
 */
import { equivalentCatalogGtin, displayEd2Gtin } from './ed2BarcodeIdentity.js'

const PRIORITY = { review: 0, matching: 1, repair: 2, identify: 3, synonyms: 4, classify: 5 }
const GTIN_SHAPE = /^(?:[0-9]{8}|[0-9]{12,14})$/

export const WORK_TYPES = [
  { key: 'review', title: 'Identificatie controleren' },
  { key: 'matching', title: 'Handmatig matchen' },
  { key: 'repair', title: 'Catalogus herstellen' },
  { key: 'identify', title: 'Identificeren' },
  { key: 'synonyms', title: 'Synoniemen' },
  { key: 'classify', title: 'Classificeren' },
]

export function projectArticleWorkQueue(receiptItems, products, classificationTasks, {
  isSuperuser = false, canClassifyGpc = true, canClassifyCbs = true,
  synonymAnalysis = null, canManageSynonyms = true,
} = {}) {
  if (!Array.isArray(receiptItems) || !Array.isArray(products) || !Array.isArray(classificationTasks)) {
    throw new Error('De werkvoorraadbronnen zijn onvolledig.')
  }

  const queue = []
  const sourceIds = new Set()
  for (const source of receiptItems) {
    const sourceId = String(source.id || '').trim()
    const name = String(source.receipt_line_text || '').trim()
    const retailer = String(source.retailer_code || '').trim()
    const number = String(source.receipt_article_number || '')
    if (!sourceId || !name || !retailer || sourceIds.has(sourceId)) {
      throw new Error('De bonartikelidentiteit is onvolledig of dubbel.')
    }
    sourceIds.add(sourceId)
    const status = String(source.identity_status || '')
    if (!['not_identified', 'saved_only', 'review', 'catalog_linked'].includes(status)) {
      throw new Error('Een bonartikel heeft een onbekende identificatiestatus.')
    }
    const manual = String(source.manual_barcode || '').trim()
    const central = String(source.article_code || '').trim()
    const explicitProduct = String(source.identity_catalog_product_id || '').trim()
    const centralProduct = String(source.catalog_product_id || '').trim()
    const differentCatalogOwners = Boolean(
      explicitProduct && centralProduct && explicitProduct !== centralProduct
    )
    // Use the same checksum-validated comparison as Identificeren:
    // GTIN-13 and a leading-zero GTIN-14 are one product identity.
    // Distinct or invalid codes must still be reviewed.
    const differentBarcodes = Boolean(
      manual && central && manual !== central && !equivalentCatalogGtin(manual, central)
    )
    const conflictingClaims = differentCatalogOwners || differentBarcodes
    if (status === 'catalog_linked' && !conflictingClaims) {
      if (!explicitProduct && !centralProduct) {
        throw new Error('Een bevestigde Cataloguskoppeling heeft geen centrale productidentiteit.')
      }
      continue
    }
    const hasClaim = Boolean(manual || central || source.identity_catalog_product_id || source.catalog_product_id)
    const manualEligible = status === 'not_identified'
      && !hasClaim && Boolean(String(source.automatic_match_review_reason || '').trim())
    let type = 'identify'
    let reason = 'Er is nog geen betrouwbaar bevestigd Catalogusproduct.'
    if (differentCatalogOwners) {
      type = 'review'
      reason = 'De bewaarde koppeling en de Cataloguskoppeling verwijzen naar verschillende Catalogusproducten.'
    } else if (differentBarcodes) {
      type = 'review'
      reason = 'De bewaarde barcode en de Catalogusbarcode verschillen; controleer welke code juist is.'
    } else if (status === 'review') {
      type = 'review'
      reason = 'Deze artikelidentiteit heeft de status Te beoordelen. Een veilige koppeling is nog niet bevestigd.'
    } else if (status === 'saved_only' && !source.identity_repairable) {
      type = 'review'
      reason = 'Barcode bewaard, maar automatisch herstel is niet veilig bewezen.'
    } else if (status === 'saved_only' && source.identity_repairable && GTIN_SHAPE.test(manual)) {
      type = 'repair'
      reason = 'Barcode bewaard; de centrale Cataloguskoppeling moet nog worden hersteld.'
    } else if (status === 'saved_only') {
      type = 'review'
      reason = 'De opgeslagen barcode kan niet zonder verdere verificatie worden hersteld.'
    } else if (manualEligible) {
      type = 'matching'
      reason = String(source.automatic_match_review_reason).trim()
    }
    // The existing Matchen write path is exclusively for platform Superusers.
    // Frontteam members receive no executable matching task or implied access.
    if (type === 'matching' && !isSuperuser) continue
    queue.push({
      key: 'receipt:' + sourceId, type, name, retailer, number, barcode: displayEd2Gtin(central || manual),
      reason, sourceId, productId: '', system: '', area: type === 'matching' ? 'matching' : 'identity',
    })
  }

  const byProduct = new Map()
  for (const product of products) {
    const id = String(product.id || '').trim()
    if (!id || byProduct.has(id)) throw new Error('De Catalogusidentiteiten zijn onvolledig of dubbel.')
    byProduct.set(id, product)
  }
  const taskKeys = new Set()
  for (const task of classificationTasks) {
    const productId = String(task.global_product_id || '').trim()
    const system = String(task.system || '')
    const key = productId + ':' + system
    if (!productId || !['gpc', 'cbs'].includes(system) || task.status !== 'open'
        || !byProduct.has(productId) || taskKeys.has(key)
        || (task.key && task.key !== key)) {
      throw new Error('De classificatiewerkvoorraad bevat een onbekende of dubbele taak.')
    }
    const product = byProduct.get(productId)
    taskKeys.add(key)
    if ((system === 'gpc' && !canClassifyGpc) || (system === 'cbs' && !canClassifyCbs)) continue
    queue.push({
      key: 'classification:' + key, type: 'classify', name: String(product.name || ''),
      retailer: '', number: '', barcode: String(product.gtin || ''),
      reason: system === 'gpc' ? 'De officiële GS1 GPC-indeling ontbreekt.'
        : 'De officiële CBS ECOICOPv2-indeling ontbreekt.',
      sourceId: '', productId, system, area: 'classify',
    })
  }

  if (synonymAnalysis !== null) {
    if (!Array.isArray(synonymAnalysis.items)
        || !Number.isSafeInteger(synonymAnalysis.summary?.candidate_pairs)
        || synonymAnalysis.summary.candidate_pairs < 0) {
      throw new Error('De synoniemanalyse is onvolledig.')
    }
    const productIds = new Set()
    let reviewProducts = 0
    for (const product of synonymAnalysis.items) {
      const id = String(product.id || '').trim()
      if (!id || productIds.has(id) || !Array.isArray(product.pending)) {
        throw new Error('De synoniemanalyse bevat ongeldige of dubbele producten.')
      }
      productIds.add(id)
      if (!product.pending.length) continue
      reviewProducts += 1
      if (!canManageSynonyms) continue
      const suggestedPeers = new Set()
      for (const suggestion of product.pending) {
        if (!suggestion.id || suggestion.id === id || suggestedPeers.has(suggestion.id)) {
          throw new Error('Een synoniemvoorstel bevat ongeldige productidentiteit.')
        }
        suggestedPeers.add(suggestion.id)
      }
      queue.push({
        key: 'synonyms:' + id, type: 'synonyms',
        name: String(product.name || ''),
        retailer: '', number: '', barcode: String(product.primary_gtin || ''),
        reason: product.pending.length + ' onbevestigde synoniemvoorstel(len); '
          + 'naamovereenkomst is nooit automatisch bewijs.',
        sourceId: '', productId: id, system: '', area: 'synonyms',
      })
    }
    if (synonymAnalysis.summary.candidate_pairs > 0 && reviewProducts === 0) {
      throw new Error('Synoniemvoorstellen ontbreken in het actuele Catalogusoverzicht.')
    }
  }

  queue.sort((a, b) => PRIORITY[a.type] - PRIORITY[b.type]
    || a.name.localeCompare(b.name, 'nl') || a.key.localeCompare(b.key))
  const counts = Object.fromEntries(WORK_TYPES.map((type) => [type.key, 0]))
  for (const task of queue) counts[task.type] += 1
  return { tasks: queue, counts }
}
