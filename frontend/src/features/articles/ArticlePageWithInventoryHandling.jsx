import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useParams } from 'react-router-dom'
import { readStoredAuthContext } from '../../lib/authSession'
import ArticlePage from './ArticlePage'
import InventoryHandlingField from './components/InventoryHandlingField'

const SETTINGS_SECTION_SELECTOR = '[data-testid="article-household-settings-section"] .rz-overview-group-body'

function resolveManagementAccess(authContext = {}) {
  const displayRole = String(authContext?.display_role || '').trim().toLowerCase()
  const canonicalRole = String(authContext?.role || '').trim().toLowerCase()
  const permissions = authContext?.permissions && typeof authContext.permissions === 'object'
    ? authContext.permissions
    : {}

  return Boolean(
    permissions['articles.manage'] === true
    || displayRole === 'admin'
    || canonicalRole === 'owner'
    || canonicalRole === 'admin'
    || canonicalRole === 'household.owner'
    || canonicalRole === 'household.admin'
  )
}

function InventoryHandlingPortal() {
  const { articleId = '' } = useParams()
  const [target, setTarget] = useState(null)
  const authContext = readStoredAuthContext() || {}
  const householdId = String(authContext?.active_household_id || authContext?.household_id || '').trim()
  const householdArticleId = String(articleId || '').trim()
  const canManage = resolveManagementAccess(authContext)

  useEffect(() => {
    function findTarget() {
      const nextTarget = document.querySelector(SETTINGS_SECTION_SELECTOR)
      setTarget((current) => current === nextTarget ? current : nextTarget)
    }

    findTarget()
    const observer = new MutationObserver(findTarget)
    observer.observe(document.body, { childList: true, subtree: true })

    return () => observer.disconnect()
  }, [])

  if (!target || !householdId || !householdArticleId) return null

  return createPortal(
    <InventoryHandlingField
      householdId={householdId}
      householdArticleId={householdArticleId}
      canManage={canManage}
    />,
    target,
  )
}

export default function ArticlePageWithInventoryHandling() {
  return (
    <>
      <ArticlePage />
      <InventoryHandlingPortal />
    </>
  )
}
