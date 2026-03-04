
import "./components/input.css";

export default function Input({ label, ...props }) {
  return (
    <label>
      {label && <div className="rz-label">{label}</div>}
      <input className="rz-input" {...props} />
    </label>
  )
}


// TABLE ROW HEIGHT DEBUG
setTimeout(()=>{
  try{
    const r=document.querySelector("tbody tr");
    if(r){console.debug("TABLE ROW HEIGHT DEBUG:", r.getBoundingClientRect().height);}
  }catch(e){}
},1000);
