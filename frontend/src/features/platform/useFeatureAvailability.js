import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../../lib/apiClient.js'

export default function useFeatureAvailability() {
  const [features, setFeatures] = useState({})
  useEffect(() => {
    let active = true
    let controller
    async function refresh() {
      controller?.abort()
      controller = new AbortController()
      try {
        const response = await fetch(`${API_BASE_URL}/api/features`, {
          credentials: 'include', cache: 'no-store', signal: controller.signal,
          headers: { Accept: 'application/json' },
        })
        if (!response.ok) throw new Error('Feature availability unavailable')
        const payload = await response.json()
        if (active) setFeatures(payload?.features || {})
      } catch (error) {
        if (active && error.name !== 'AbortError') setFeatures({})
      }
    }
    refresh()
    window.addEventListener('focus', refresh)
    window.addEventListener('rezzerv-features-changed', refresh)
    const timer = window.setInterval(refresh, 30000)
    return () => {
      active = false
      controller?.abort()
      window.clearInterval(timer)
      window.removeEventListener('focus', refresh)
      window.removeEventListener('rezzerv-features-changed', refresh)
    }
  }, [])
  return features
}
