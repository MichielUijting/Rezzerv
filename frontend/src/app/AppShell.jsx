import Header from '../ui/Header.jsx'
import Button from '../ui/Button.jsx'

export default function AppShell({ title, children, showExit = true }) {
  return (
    <div className="rz-screen">
      <Header title={title} />
      <div className="rz-content">
        <div className="rz-content-inner">
          {children}
        </div>
      </div>

      {showExit && (
        <div className="rz-exitbar">
          <Button variant="secondary" onClick={() => window.close()}>
            Afsluiten
          </Button>
        </div>
      )}
    </div>
  )
}


// TABLE ROW HEIGHT DEBUG
setTimeout(()=>{
  try{
    const r=document.querySelector("tbody tr");
    if(r){console.debug("TABLE ROW HEIGHT DEBUG:", r.getBoundingClientRect().height);}
  }catch(e){}
},1000);
