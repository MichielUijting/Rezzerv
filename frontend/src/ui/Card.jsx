
export default function Card({ children, className = "" }) {
  return (
    <div className={`rz-card ${className}`.trim()}>
      {children}
    </div>
  );
}


// TABLE ROW HEIGHT DEBUG
setTimeout(()=>{
  try{
    const r=document.querySelector("tbody tr");
    if(r){console.debug("TABLE ROW HEIGHT DEBUG:", r.getBoundingClientRect().height);}
  }catch(e){}
},1000);
