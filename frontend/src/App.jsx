import AppRouter from "./app/router/AppRouter";
import { getRezzervVersionTag } from "./ui/version";

export default function App() {
  const buildTag = getRezzervVersionTag();
  return (
    <>
      <AppRouter />
      <div className="rz-buildtag" aria-hidden="true">Rezzerv v{buildTag}</div>
    </>
  );
}


// TABLE ROW HEIGHT DEBUG
setTimeout(()=>{
  try{
    const r=document.querySelector("tbody tr");
    if(r){console.debug("TABLE ROW HEIGHT DEBUG:", r.getBoundingClientRect().height);}
  }catch(e){}
},1000);
