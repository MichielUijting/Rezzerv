import { useEffect, useState } from "react";

export default function Tabs({ tabs, defaultTab, activeTab = null, onTabChange = null, children, tabTestIdMap = {}, activeColor = null }) {
  const initialTab = activeTab ?? defaultTab ?? tabs[0];
  const [active, setActive] = useState(initialTab);

  useEffect(() => {
    if (activeTab && activeTab !== active) {
      setActive(activeTab);
    }
  }, [activeTab, active]);

  function handleTabChange(tab) {
    if (activeTab == null) {
      setActive(tab);
    }
    onTabChange?.(tab);
  }

  const currentActive = activeTab ?? active;

  return (
    <div className="rz-tabs" data-testid="tabs-root">
      <div className="rz-tabbar" role="tablist" aria-label="Artikeldetails tabs" data-testid="tabs-tablist">
        {tabs.map((t) => {
          const isActive = currentActive === t;
          return (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={isActive}
              className={isActive ? "rz-tab rz-tab-active" : "rz-tab"}
              onClick={() => handleTabChange(t)}
              data-testid={tabTestIdMap[t]}
              style={isActive && activeColor ? { borderColor: activeColor, background: "#ffffff", color: activeColor, fontWeight: 700, boxShadow: `inset 0 -2px 0 ${activeColor}` } : undefined}
            >
              {t}
            </button>
          );
        })}
      </div>

      <div className="rz-tabcontent"><div className="rz-tabpanel-shell">{children(currentActive)}</div></div>
    </div>
  );
}
