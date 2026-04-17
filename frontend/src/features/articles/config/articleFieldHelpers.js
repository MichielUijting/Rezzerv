import { articleFieldConfig } from './articleFieldConfig'
import { ARTICLE_TABS } from './articleFieldConstants'

export function getFieldsByTab(tab) {
  return articleFieldConfig.filter((field) => field.tab === tab).sort((a, b) => a.order - b.order)
}

export function getFieldsByTabAndGroup(tab) {
  return getFieldsByTab(tab).reduce((acc, field) => {
    if (!acc[field.group]) acc[field.group] = []
    acc[field.group].push(field)
    return acc
  }, {})
}

export function getAlwaysVisibleFieldKeys() {
  return articleFieldConfig.filter((field) => field.visibilityType === 'always').map((field) => field.key)
}

export function getDefaultVisibilityMap() {
  const map = {}
  Object.values(ARTICLE_TABS).forEach((tab) => {
    map[tab] = {}
  })
  articleFieldConfig.forEach((field) => {
    map[field.tab][field.key] = field.visibilityType === 'always' || field.visibilityType === 'default_on'
  })
  return map
}
