function normalizedEntries(row) {
  return (Array.isArray(row?.inventoryEntries) ? row.inventoryEntries : [])
    .map((entry, index) => ({
      inventoryId: String(entry?.inventoryId || '').trim(),
      quantity: Number(entry?.quantity ?? 0),
      sourceIndex: Number.isFinite(Number(entry?.sourceIndex)) ? Number(entry.sourceIndex) : index,
    }))
    .filter((entry) => entry.inventoryId && Number.isFinite(entry.quantity) && entry.quantity > 0)
    .sort((a, b) => b.quantity - a.quantity || a.sourceIndex - b.sourceIndex || a.inventoryId.localeCompare(b.inventoryId))
}

export function selectQuickInventoryTarget(row, direction) {
  const entries = normalizedEntries(row)
  if (direction === 'decrease') {
    return entries.find((entry) => entry.quantity >= 1) || null
  }
  if (direction === 'increase') {
    return entries[0] || null
  }
  return null
}

export function buildQuickInventoryMutation(row, direction) {
  const target = selectQuickInventoryTarget(row, direction)
  if (!target) return null

  if (direction === 'decrease') {
    return {
      inventory_id: target.inventoryId,
      quantity: 1,
      event_type: 'consume',
      note: 'Snelle afboeking via mobiele Voorraad.',
    }
  }

  if (direction === 'increase') {
    return {
      inventory_id: target.inventoryId,
      quantity: target.quantity + 1,
      event_type: 'adjustment',
      note: 'Snelle ophoging via mobiele Voorraad.',
    }
  }

  return null
}
