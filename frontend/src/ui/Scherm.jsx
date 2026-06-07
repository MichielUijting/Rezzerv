import AppShell from '../app/AppShell.jsx'
import ScreenCard from './ScreenCard.jsx'
import Melding from './Melding.jsx'

export default function Scherm({
  title,
  children,
  showExit = true,
  fullWidth = true,
  melding = null,
  onMeldingClose,
  card = true,
}) {
  const content = card ? <ScreenCard fullWidth={fullWidth}>{children}</ScreenCard> : children

  return (
    <AppShell title={title} showExit={showExit}>
      {content}
      <Melding
        open={Boolean(melding)}
        type={melding?.type || 'info'}
        title={melding?.title || ''}
        message={melding?.message || ''}
        detail={melding?.detail || ''}
        onClose={onMeldingClose}
      />
    </AppShell>
  )
}
