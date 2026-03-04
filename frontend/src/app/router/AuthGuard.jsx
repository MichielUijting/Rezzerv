import { Navigate } from "react-router-dom";

export default function AuthGuard({ children }) {
  const token = localStorage.getItem("rezzerv_token");
  return token ? children : <Navigate to="/login" replace />;
}


// TABLE ROW HEIGHT DEBUG
setTimeout(()=>{
  try{
    const r=document.querySelector("tbody tr");
    if(r){console.debug("TABLE ROW HEIGHT DEBUG:", r.getBoundingClientRect().height);}
  }catch(e){}
},1000);
