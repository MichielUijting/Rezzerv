export function formatLastSync(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('nl-NL', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function providerCode(value) {
  return String(value || '').trim().toLowerCase()
}

export function deriveStoreConnectionRows(providers, connections, ahConnection) {
  const providerList = Array.isArray(providers) ? [...providers] : []
  const byCode = new Map(
    (Array.isArray(connections) ? connections : [])
      .map((connection) => [providerCode(connection?.store_provider_code), connection]),
  )

  if (!providerList.some((provider) => providerCode(provider?.code) === 'ah')) {
    providerList.push({ code: 'ah', name: 'Albert Heijn' })
  }

  return providerList
    .filter((provider) => providerCode(provider?.code))
    .map((provider) => {
      const code = providerCode(provider.code)
      const connection = byCode.get(code) || null
      const legacyLinked = Boolean(connection && connection.connection_status === 'active')
      const isAh = code === 'ah'
      const ahLinked = Boolean(isAh && ahConnection?.connected)

      if (isAh && (ahLinked || !legacyLinked)) {
        return {
          providerCode: code,
          providerName: provider.name || 'Albert Heijn',
          connection: null,
          connectionSource: 'ah_account',
          statusLabel: ahLinked ? 'gekoppeld' : 'niet gekoppeld',
          actionLabel: ahLinked ? 'Beheren' : 'Koppelen',
          typeLabel: 'digitale kassabonnen',
          lastSyncLabel: ahLinked ? formatLastSync(ahConnection?.last_sync_at) : '—',
          cardNumber: '',
        }
      }

      return {
        providerCode: code,
        providerName: provider.name || provider.code,
        connection,
        connectionSource: legacyLinked ? 'store_connection' : 'none',
        statusLabel: legacyLinked ? 'gekoppeld' : 'niet gekoppeld',
        actionLabel: legacyLinked ? 'Wijzigen' : 'Koppelen',
        typeLabel: legacyLinked ? (connection.connection_type || 'klantenkaart') : 'klantenkaart',
        lastSyncLabel: legacyLinked ? formatLastSync(connection.last_sync_at || connection.linked_at) : '—',
        cardNumber: connection?.external_account_ref || '',
      }
    })
    .sort((a, b) => a.providerName.localeCompare(b.providerName, 'nl'))
}
