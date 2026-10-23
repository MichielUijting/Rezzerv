import Button from '../../ui/Button'
import Input from '../../ui/Input'
import './retailerReceiptPanel.css'

/**
 * Single visual contract for browser-assisted receipt providers.
 * Provider-specific import and authorization logic stays in the caller.
 */
export default function RetailerReceiptPanel({
  retailer,
  testId,
  isMobileViewport,
  from,
  to,
  fromTestId,
  toTestId,
  dateRangeTestId,
  datesDisabled = false,
  onFromChange,
  onToChange,
  openHref,
  openTestId,
  onOpen,
  openDisabled = false,
  openBusy = false,
  helpTestId,
  onHelp,
  periodError,
  setupHelp,
  children,
}) {
  const actionStyle = {
    display: 'inline-flex',
    width: '100%',
    height: '100%',
    minHeight: '40px',
    minWidth: 0,
    alignItems: 'center',
    justifyContent: 'center',
    boxSizing: 'border-box',
    textAlign: 'center',
    whiteSpace: 'normal',
  }

  return (
    <div
      data-testid={testId}
      className={isMobileViewport ? 'rz-store-receipt-panel--mobile' : undefined}
      style={{ display: 'grid', rowGap: '12px', maxWidth: '760px', minWidth: 0 }}
    >
      <div>
        <h3 style={{ margin: 0 }}>{retailer} digitale kassabonnen</h3>
        {isMobileViewport ? (
          <p role="status" style={{ margin: '6px 0 0' }}>
            Voor het ophalen is momenteel een browser met ondersteuning voor JavaScript-favorieten nodig.
            Dit werkt niet betrouwbaar in alle mobiele browsers.
          </p>
        ) : null}
        <p style={{ margin: '6px 0 0' }}>
          Kies de periode en haal je kassabonnen op.
        </p>
      </div>

      <div
        data-testid={dateRangeTestId || 'retailer-receipt-date-range'}
        style={{ display: 'flex', columnGap: '12px', rowGap: '12px', flexWrap: 'wrap' }}
      >
        <Input
          label="Vanaf"
          type="date"
          value={from}
          onChange={onFromChange}
          disabled={datesDisabled}
          data-testid={fromTestId}
        />
        <Input
          label="Tot en met"
          type="date"
          value={to}
          onChange={onToChange}
          disabled={datesDisabled}
          data-testid={toTestId}
        />
      </div>

      {periodError ? <div role="alert">{periodError}</div> : null}

      <div
        data-testid="retailer-receipt-action-row"
        style={{
          display: 'grid',
          gridTemplateColumns: isMobileViewport
            ? 'minmax(0, 1fr) minmax(0, 1.5fr)'
            : 'minmax(0, 160px) minmax(0, 240px)',
          alignItems: 'stretch',
          justifyContent: 'space-between',
          gap: '8px',
        }}
      >
        {openHref ? (
          <a
            href={openHref}
            role="button"
            className="rz-button-primary"
            style={{ ...actionStyle, textDecoration: 'none' }}
            onClick={onOpen}
            data-testid={openTestId}
          >Open mijn {retailer}</a>
        ) : (
          <Button
            type="button"
            onClick={onOpen}
            disabled={openDisabled}
            style={actionStyle}
            data-testid={openTestId}
          >{openBusy ? `${retailer} voorbereiden…` : `Open mijn ${retailer}`}</Button>
        )}
        <Button
          type="button"
          variant="secondary"
          style={actionStyle}
          onClick={onHelp}
          data-testid={helpTestId}
        >Eerste keer koppelen met {retailer}?</Button>
      </div>
      {setupHelp}
      {children}
    </div>
  )
}
