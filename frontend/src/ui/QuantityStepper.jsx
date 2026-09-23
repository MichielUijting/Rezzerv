import './mobileComponents.css'

export default function QuantityStepper({
  value,
  decreaseDisabled = false,
  increaseDisabled = false,
  onDecrease,
  onIncrease,
  decreaseLabel = 'Aantal met 1 verlagen',
  increaseLabel = 'Aantal met 1 verhogen',
  valueLabel = '',
  testIdPrefix = 'quantity-stepper',
  decreaseTestId = '',
  increaseTestId = '',
  valueTestId = '',
}) {
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
      <span
        className="rz-quantity-stepper-value"
        aria-label={valueLabel || `Aantal ${value}`}
        data-testid={valueTestId || undefined}
      >
        {value}
      </span>
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
