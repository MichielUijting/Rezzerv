
import React from "react";

export default function ScreenCard({children, fullWidth=false, style: styleOverride={}}){

  const style = {
    background:"#fff",
    padding:"20px",
    borderRadius:"8px",
    width:"100%",
    maxWidth: fullWidth ? "none" : "900px",
    margin:"0 auto",
    minWidth: 0,
    overflow: "hidden"
  };
  const mergedStyle = {...style, ...styleOverride};

  return (
    <div style={mergedStyle} data-testid="screen-card">
      {children}
    </div>
  );
}
