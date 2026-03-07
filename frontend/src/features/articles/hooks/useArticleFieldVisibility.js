import { useCallback, useEffect, useMemo, useState } from 'react'
import { getAlwaysVisibleFieldKeys, getDefaultVisibilityMap } from '../config/articleFieldHelpers'
import { fetchArticleFieldVisibility, saveArticleFieldVisibility } from '../services/articleFieldVisibilityService'

function clone(obj) {
  return JSON.parse(JSON.stringify(obj))
}

function merge(defaults, overrides) {
  const merged = clone(defaults)
  if (!overrides || typeof overrides !== 'object') return merged
  Object.keys(merged).forEach((tab) => {
    const tabOverrides = overrides[tab]
    if (!tabOverrides || typeof tabOverrides !== 'object') return
    Object.keys(tabOverrides).forEach((key) => {
      if (key in merged[tab] && typeof tabOverrides[key] === 'boolean') merged[tab][key] = tabOverrides[key]
    })
  })
  return merged
}

function forceAlwaysVisible(map, alwaysVisibleKeys) {
  const next = clone(map)
  Object.keys(next).forEach((tab) => {
    Object.keys(next[tab]).forEach((key) => {
      if (alwaysVisibleKeys.includes(key)) next[tab][key] = true
    })
  })
  return next
}

export function useArticleFieldVisibility() {
  const defaultVisibility = useMemo(() => getDefaultVisibilityMap(), [])
  const alwaysVisibleKeys = useMemo(() => getAlwaysVisibleFieldKeys(), [])
  const [visibilityMap, setVisibilityMap] = useState(forceAlwaysVisible(defaultVisibility, alwaysVisibleKeys))
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const overrides = await fetchArticleFieldVisibility()
      setVisibilityMap(forceAlwaysVisible(merge(defaultVisibility, overrides), alwaysVisibleKeys))
    } catch (err) {
      setVisibilityMap(forceAlwaysVisible(defaultVisibility, alwaysVisibleKeys))
      setError(err)
    } finally {
      setIsLoading(false)
    }
  }, [defaultVisibility, alwaysVisibleKeys])

  useEffect(() => { load() }, [load])

  const toggleFieldVisibility = useCallback((tab, fieldKey) => {
    if (alwaysVisibleKeys.includes(fieldKey)) return
    setVisibilityMap((current) => {
      if (!current?.[tab] || !(fieldKey in current[tab])) return current
      return { ...current, [tab]: { ...current[tab], [fieldKey]: !current[tab][fieldKey] } }
    })
  }, [alwaysVisibleKeys])

  const resetToDefault = useCallback(() => {
    setVisibilityMap(forceAlwaysVisible(defaultVisibility, alwaysVisibleKeys))
  }, [defaultVisibility, alwaysVisibleKeys])

  const showAllFields = useCallback(() => {
    const allVisible = clone(defaultVisibility)
    Object.keys(allVisible).forEach((tab) => {
      Object.keys(allVisible[tab]).forEach((key) => { allVisible[tab][key] = true })
    })
    setVisibilityMap(forceAlwaysVisible(allVisible, alwaysVisibleKeys))
  }, [defaultVisibility, alwaysVisibleKeys])

  const saveVisibility = useCallback(async () => {
    setIsSaving(true)
    setError(null)
    try {
      const saved = await saveArticleFieldVisibility(forceAlwaysVisible(visibilityMap, alwaysVisibleKeys))
      const merged = forceAlwaysVisible(merge(defaultVisibility, saved), alwaysVisibleKeys)
      setVisibilityMap(merged)
      return { ok: true, data: merged }
    } catch (err) {
      setError(err)
      return { ok: false, error: err }
    } finally {
      setIsSaving(false)
    }
  }, [visibilityMap, defaultVisibility, alwaysVisibleKeys])

  return { visibilityMap, alwaysVisibleKeys, defaultVisibility, isLoading, isSaving, error, toggleFieldVisibility, resetToDefault, showAllFields, saveVisibility, reloadVisibility: load }
}
