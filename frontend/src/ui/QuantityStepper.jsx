import { useEffect, useRef, useState } from 'react'
import './mobileComponents.css'

function parseEditableQuantity(value) {
  const normalized = String(value ?? '').trim().replace(',', '.')
  if (!normalized || !/^\d*(?:\.\d*)?$/.test(normalized)) return null
  const parsed = Number(normalized)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null
}

export default function QuantityStepper({
  value,
  decreaseDisabled = false,
  increaseDisabled = false,
  valueEditable = false,
  valueDisabled = false,
  onDecrease,
  onIncrease,
  onValueCommit,
  decreaseLabel = 'Aantal met 1 verlagen',
  increaseLabel = 'Aantal met 1 verhogen',
  valueLabel = '',
  testIdPrefix = 'quantity-stepper',
  decreaseTestId = '',
  increaseTestId = '',
  valueTestId = '',
}) {
  const editableValue = valueEditable && typeof onValueCommit === 'function'
  const [draftValue, setDraftValue] = useState(String(value ?? ''))
  const [editingValue, setEditingValue] = useState(false)
  const skipCommitRef = useRef(false)

  useEffect(() => {
    if (!editingValue) setDraftValue(String(value ?? ''))
  }, [editingValue, value])

  function stopPropagation(event) {
    event.stopPropagation()
  }

  function commitDraft(event) {
    event.stopPropagation()
    if (skipCommitRef.current) {
      skipCommitRef.current = false
      setEditingValue(false)
      setDraftValue(String(value ?? ''))
      return
    }

    const parsed = parseEditableQuantity(draftValue)
    setEditingValue(false)
    if (parsed == null) {
      setDraftValue(String(value ?? ''))
      return
    }

    setDraftValue(String(parsed))
    const currentValue = parseEditableQuantity(value)
    if (currentValue == null || parsed !== currentValue) onValueCommit(parsed)
  }

  function handleValueKeyDown(event) {
    event.stopPropagation()
    if (event.key === 'Enter') {
      event.preventDefault()
      event.currentTarget.blur()
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      skipCommitRef.current = true
      setDraftValue(String(value ?? ''))
      event.currentTarget.blur()
    }
  }

  return (
    <div className="rz-quantity-stepper">
      <button
        type="button"
        className="rz-quantity-stepper-button"
        disabled={decreaseDisabled}
        aria-label={decreaseLabel}
        data-testid={decreaseTestId || `${testIdPrefix}-decrease`}
        onClick={onDecrease}
      >
        −
      </button>
      {editableValue ? (
        <input
          type="text"
          inputMode="decimal"
          enterKeyHint="done"
          className="rz-quantity-stepper-value rz-quantity-stepper-value--editable"
          value={draftValue}
          disabled={valueDisabled}
          aria-label={valueLabel || `Aantal ${value}. Tik om aan te passen`}
          data-testid={valueTestId || `${testIdPrefix}-value`}
          onPointerDown={stopPropagation}
          onClick={stopPropagation}
          onFocus={(event) => {
            event.stopPropagation()
            setEditingValue(true)
            setDraftValue(String(value ?? ''))
            event.currentTarget.select()
          }}
          onChange={(event) => setDraftValue(event.target.value)}
          onBlur={commitDraft}
          onKeyDown={handleValueKeyDown}
        />
      ) : (
        <span
          className="rz-quantity-stepper-value"
          aria-label={valueLabel || `Aantal ${value}`}
          data-testid={valueTestId || undefined}
          onPointerDown={stopPropagation}
          onClick={stopPropagation}
        >
          {value}
        </span>
      )}
      <button
        type="button"
        className="rz-quantity-stepper-button"
        disabled={increaseDisabled}
        aria-label={increaseLabel}
        data-testid={increaseTestId || `${testIdPrefix}-increase`}
        onClick={onIncrease}
      >
        +
      </button>
    </div>
  )
}
