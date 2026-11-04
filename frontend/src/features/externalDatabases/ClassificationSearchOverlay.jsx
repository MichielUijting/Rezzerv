import { useEffect, useRef } from 'react'
import Button from '../../ui/Button'

/** Shared accessible chooser: data is supplied by the official GS1/CBS APIs. */
export default function ClassificationSearchOverlay({
  title, query, onQueryChange, rows, onChoose, onClose, busy = false,
  emptyMessage = 'Geen categorieën gevonden.', getKey, getTitle, getDetail,
  children,
}) {
  const inputRef = useRef(null)
  useEffect(() => {
    inputRef.current?.focus()
    function onKeyDown(event) {
      if (event.key === 'Escape' && !busy) onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [busy, onClose])
  return <div className="rz-modal-backdrop rz-classification-overlay-backdrop"
    onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose() }}>
    <section className="rz-classification-search-overlay" role="dialog" aria-modal="true" aria-label={title}>
      <div className="rz-classification-overlay-heading">
        <h3>{title}</h3>
        <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>Sluiten</Button>
      </div>
      <label className="rz-input-field">
        <span className="rz-label">Zoeken op code of omschrijving</span>
        <input ref={inputRef} className="rz-input" value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Zoek categorie of code" disabled={busy} />
      </label>
      {children}
      <div className="rz-classification-overlay-results" aria-label="Classificatieresultaten">
        {rows.length ? rows.map((row) => <button type="button" key={getKey(row)}
          className="rz-classification-overlay-row"
          disabled={busy} onClick={() => onChoose(row)}>
          <strong>{getTitle(row)}</strong>
          {getDetail(row) ? <span>{getDetail(row)}</span> : null}
        </button>) : <p role="status">{busy ? 'Categorieën laden…' : emptyMessage}</p>}
      </div>
    </section>
  </div>
}
