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
}) {
  return (
    <div className="rz-quantity-stepper">
      <button
        type="button"
        className="rz-quantity-stepper-button"
        disabled={decreaseDisabled}
        aria-label={decreaseLabel}
        data-testid={`${testIdPrefix}-decrease`}
        onClick={onDecrease}
      >
        −
      </button>
      <span className="rz-quantity-stepper-value" aria-label={valueLabel || `Aantal ${value}`}>
        {value}
      </span>
      <button
        type="button"
        className="rz-quantity-stepper-button"
        disabled={increaseDisabled}
        aria-label={increaseLabel}
        data-testid={`${testIdPrefix}-increase`}
        onClick={onIncrease}
      >
        +
      </button>
    </div>
  )
}
