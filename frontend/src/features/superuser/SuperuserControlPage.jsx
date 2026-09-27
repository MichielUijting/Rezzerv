import { useState } from 'react'
import Header from '../../ui/Header.jsx'
import ScreenCard from '../../ui/ScreenCard.jsx'
import SuperuserDashboardPage from './SuperuserDashboardPage.jsx'
import SuperuserActionButtonsSection from './SuperuserActionButtonsSection.jsx'
import SuperuserLoginBackgroundSection from './SuperuserLoginBackgroundSection.jsx'

const SUPERUSER_TABS = ['Beheercentrum', 'Actieknoppen', 'Inlogscherm']

export default function SuperuserControlPage() {
  const [activeTab, setActiveTab] = useState('Beheercentrum')

  return (
    <div data-testid="superuser-control-page">
      <div style={{ padding: '12px 24px 0', background: '#f7faf7', borderBottom: '1px solid #d4ddd4' }}>
        <div className="rz-tabbar" role="tablist" aria-label="Superuser beheer-tabs" data-testid="superuser-control-tabs">
          {SUPERUSER_TABS.map((tab) => {
            const active = activeTab === tab
            return (
              <button
                key={tab}
                type="button"
                role="tab"
                aria-selected={active}
                className={active ? 'rz-tab rz-tab-active' : 'rz-tab'}
                onClick={() => setActiveTab(tab)}
                data-testid={`superuser-control-tab-${tab === 'Beheercentrum' ? 'dashboard' : tab === 'Actieknoppen' ? 'action-buttons' : 'login-background'}`}
              >
                {tab}
              </button>
            )
          })}
        </div>
      </div>

      {activeTab === 'Beheercentrum' ? (
        <SuperuserDashboardPage />
      ) : (
        <div className="rz-screen" data-testid={activeTab === 'Actieknoppen' ? 'superuser-action-buttons-page' : 'superuser-login-background-page'}>
          <Header title="Inhuis Beheercentrum" />
          <div className="rz-content">
            <div className="rz-content-inner">
              <ScreenCard fullWidth>
                {activeTab === 'Actieknoppen' ? <SuperuserActionButtonsSection /> : <SuperuserLoginBackgroundSection />}
              </ScreenCard>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
