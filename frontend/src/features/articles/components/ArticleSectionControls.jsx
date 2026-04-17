import { useEffect, useState } from 'react'

export function ArticleGlobalSectionToggle({ onExpandAll, onCollapseAll, ariaLabelPrefix, canExpand = true, canCollapse = true }) {
  return (
    <div className="rz-article-global-toggle" aria-label={`${ariaLabelPrefix} secties in- of uitklappen`}>
      <button
        type="button"
        className="rz-article-collapsible-toggle rz-article-global-toggle-button"
        onClick={onExpandAll}
        aria-label={`${ariaLabelPrefix} alle secties uitklappen`}
        disabled={!canExpand}
      >
        <span className="rz-article-collapsible-icon" aria-hidden="true">+</span>
      </button>
      <button
        type="button"
        className="rz-article-collapsible-toggle rz-article-global-toggle-button"
        onClick={onCollapseAll}
        aria-label={`${ariaLabelPrefix} alle secties inklappen`}
        disabled={!canCollapse}
      >
        <span className="rz-article-collapsible-icon" aria-hidden="true">−</span>
      </button>
    </div>
  )
}

export function ArticleSectionAccordion({
  title,
  children,
  defaultOpen = true,
  testId = null,
  headerActions = null,
  forceOpenState = null,
  forceToggleVersion = 0,
  open: controlledOpen = undefined,
  onToggle = null,
  sectionClassName = '',
  titleClassName = '',
  contentClassName = '',
}) {
  const [localOpen, setLocalOpen] = useState(defaultOpen)
  const open = typeof controlledOpen === 'boolean' ? controlledOpen : localOpen

  useEffect(() => {
    if (typeof forceOpenState === 'boolean' && typeof controlledOpen !== 'boolean') {
      setLocalOpen(forceOpenState)
    }
  }, [controlledOpen, forceOpenState, forceToggleVersion])

  function handleToggle() {
    if (typeof onToggle === 'function') {
      onToggle()
      return
    }
    setLocalOpen((current) => !current)
  }

  const mergedSectionClassName = ['rz-article-section-accordion', sectionClassName].filter(Boolean).join(' ')
  const mergedTitleClassName = ['rz-article-section-title', titleClassName].filter(Boolean).join(' ')
  const mergedContentClassName = ['rz-article-section-content', contentClassName].filter(Boolean).join(' ')

  return (
    <section className={mergedSectionClassName} data-testid={testId}>
      <div className="rz-article-section-header">
        <button
          type="button"
          className="rz-article-section-summary"
          onClick={handleToggle}
          aria-expanded={open}
        >
          <span className="rz-article-collapsible-icon" aria-hidden="true">{open ? '−' : '+'}</span>
          <span className={mergedTitleClassName}>{title}</span>
        </button>
        {headerActions ? <div className="rz-article-section-actions">{headerActions}</div> : null}
      </div>
      {open ? <div className={mergedContentClassName}>{children}</div> : null}
    </section>
  )
}
