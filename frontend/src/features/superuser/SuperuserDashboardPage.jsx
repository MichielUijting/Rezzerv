import Header from '../../ui/Header.jsx'
import ScreenCard from '../../ui/ScreenCard.jsx'
import Tabs from '../../ui/Tabs.jsx'

const TABS = ['Overzicht', 'Huishoudens', 'Gebruik', 'Kassabonnen', 'Systeem']

function EmptySection({ title }) {
  return (
    <section aria-label={title}>
      <h2 style={{ marginTop: 0, fontSize: 20 }}>{title}</h2>
      <p style={{ marginBottom: 0 }}>
        Dit onderdeel wordt in een volgende Superuser-release gevuld. S1 levert uitsluitend het veilige beheerfundament.
      </p>
    </section>
  )
}

export default function SuperuserDashboardPage() {
  return (
    <div className="rz-screen" data-testid="superuser-dashboard">
      <Header title="Rezzerv Beheercentrum" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <ScreenCard fullWidth>
            <div
              role="status"
              aria-label="Superuser alleen-lezen status"
              style={{
                marginBottom: 16,
                padding: '10px 12px',
                border: '1px solid #d4ddd4',
                borderRadius: 6,
                background: '#f7faf7',
              }}
            >
              <strong>Superuser</strong> — beheercentrum. Huishoudinzage wordt standaard alleen-lezen ingericht.
            </div>
            <Tabs tabs={TABS} defaultTab="Overzicht">
              {(activeTab) => <EmptySection title={activeTab} />}
            </Tabs>
          </ScreenCard>
        </div>
      </div>
    </div>
  )
}
