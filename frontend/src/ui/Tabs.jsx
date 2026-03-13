import { useState } from "react";

export default function Tabs({ tabs, defaultTab, children }) {
  const [active, setActive] = useState(defaultTab || tabs[0]);

  return (
    <div className="rz-tabs">
      <div className="rz-tabbar" role="tablist" aria-label="Artikeldetails tabs">
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
