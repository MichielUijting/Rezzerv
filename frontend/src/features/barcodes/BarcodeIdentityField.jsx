import Button from '../../ui/Button'
import Input from '../../ui/Input'

export default function BarcodeIdentityField({
  lineId,
  value,
  disabled = false,
  state = { status: 'idle', message: '' },
  onChange,
  onValidate,
  onScan,
}) {
  const busy = state.status === 'loading'
  return (
    <div className="rz-barcode-field" data-testid={`receipt-line-barcode-field-${lineId}`}>
      <Input
        value={value}
        onChange={(event) => onChange?.(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') onValidate?.()
        }}
        inputMode="numeric"
        autoComplete="off"
        placeholder="GTIN scannen of invullen"
        aria-label={`GTIN voor bonregel ${lineId}`}
        disabled={disabled || busy}
        data-testid={`receipt-line-barcode-input-${lineId}`}
      />
      <div className="rz-barcode-field__actions">
        <Button
          type="button"
          variant="secondary"
          onClick={onScan}
          disabled={disabled || busy}
          data-testid={`receipt-line-barcode-scan-${lineId}`}
        >
          Scannen
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={onValidate}
          disabled={disabled || busy || !String(value || '').trim()}
          data-testid={`receipt-line-barcode-check-${lineId}`}
        >
          {busy ? 'Controleren…' : 'Controleren'}
        </Button>
      </div>
    </div>
  )
}
