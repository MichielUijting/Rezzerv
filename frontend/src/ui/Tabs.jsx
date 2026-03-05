
import { useState } from "react";
import Button from "./Button";

export default function Tabs({ tabs, defaultTab, children }) {

  const [active,setActive] = useState(defaultTab || tabs[0]);

  return (
    <div>

      <div style={{display:"flex",gap:"8px",marginBottom:"16px"}}>
        {tabs.map(t => (
          <Button
            key={t}
            variant={active===t ? "primary" : "secondary"}
            onClick={()=>setActive(t)}
          >
            {t}
          </Button>
        ))}
      </div>

      {children(active)}

    </div>
  );
}
