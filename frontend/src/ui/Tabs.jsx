
import { useState } from "react";

export default function Tabs({ tabs, defaultTab, children }) {

  const [active,setActive] = useState(defaultTab || tabs[0]);

  return (
    <div className="rz-tabs">

      <div className="rz-tabbar">
        {tabs.map(t => (
          <div
            key={t}
            className={active===t ? "rz-tab rz-tab-active" : "rz-tab"}
            onClick={()=>setActive(t)}
          >
            {t}
          </div>
        ))}
      </div>

      <div className="rz-tabcontent">
        {children(active)}
      </div>

      <style jsx>{`
        .rz-tabbar{
          display:flex;
          gap:24px;
          border-bottom:1px solid #ddd;
          margin-bottom:16px;
        }

        .rz-tab{
          padding:6px 4px;
          cursor:pointer;
          color:#444;
        }

        .rz-tab-active{
          border-bottom:2px solid #1f6f43;
          font-weight:600;
          color:#000;
        }

        .rz-tabcontent{
          padding-top:8px;
        }
      `}</style>

    </div>
  );
}
