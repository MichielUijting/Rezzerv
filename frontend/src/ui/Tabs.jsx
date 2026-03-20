import { useState } from "react";

export default function Tabs({ tabs, defaultTab, children, tabTestIdMap = {}, activeColor = null }) {
  const [active, setActive] = useState(defaultTab || tabs[0]);

  return (
    <div className="rz-tabs" data-testid="tabs-root">
      <div className="rz-tabbar" role="tablist" aria-label="Artikeldetails tabs" data-testid="tabs-tablist">
        {tabs.map((t) => {
          const isActive = active === t;
          return (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={isActive}
              className={isActive ? "rz-tab rz-tab-active" : "rz-tab"}
              onClick={() => setActive(t)}
              data-testid={tabTestIdMap[t]}
              style={isActive && activeColor ? { borderColor: activeColor, background: activeColor, color: "#ffffff", fontWeight: 700 } : undefined}
            >
              {t}
            </button>
          );
        })}
      </div>

      <div className="rz-tabcontent"><div className="rz-tabpanel-shell">{children(active)}</div></div>
    </div>
  );
}
