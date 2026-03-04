// Central place for the build/version label shown in the UI.
//
// Preferred flow:
// - start.bat reads VERSION.txt into the env var REZZERV_VERSION
// - docker-compose passes REZZERV_VERSION as a build ARG to the frontend image
// - frontend/Dockerfile exposes it to Vite as VITE_REZZERV_VERSION

export function getRezzervVersionTag() {
  const injected = import.meta.env?.VITE_REZZERV_VERSION;
  if (typeof injected === "string" && injected.trim().length > 0) {
    return injected.trim();
  }

  // Fallback for local dev.
  return "Rezzerv-dev";
}


// TABLE ROW HEIGHT DEBUG
setTimeout(()=>{
  try{
    const r=document.querySelector("tbody tr");
    if(r){console.debug("TABLE ROW HEIGHT DEBUG:", r.getBoundingClientRect().height);}
  }catch(e){}
},1000);
