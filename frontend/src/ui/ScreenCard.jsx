
import React from "react";

export default function ScreenCard({children, fullWidth=false}){

  const style = {
    background:"#fff",
    padding:"24px",
    borderRadius:"16px",
    border:"2px solid #1f6f4a",
    boxShadow:"0 4px 10px rgba(0,0,0,0.08)",
    width:"100%",
    maxWidth: fullWidth ? "none" : "900px",
    margin:"0 auto"
  };

  return (
    <div style={style}>
      {children}
    </div>
  );
}
