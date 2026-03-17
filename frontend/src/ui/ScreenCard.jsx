
import React from "react";

export default function ScreenCard({children, fullWidth=false}){

  const style = {
    background:"#fff",
    padding:"20px",
    borderRadius:"8px",
    width:"100%",
    maxWidth: fullWidth ? "none" : "900px",
    margin:"0 auto"
  };

  return (
    <div style={style} data-testid="screen-card">
      {children}
    </div>
  );
}
