import { useMemo, useState } from 'react'

export function useAuth() {
  const [token, setToken] = useState(() => localStorage.getItem('rezzerv_token') || '')

  const isLoggedIn = useMemo(() => Boolean(token), [token])

  function setSession(newToken) {
    localStorage.setItem('rezzerv_token', newToken)
    setToken(newToken)
  }

  function clearSession() {
    localStorage.removeItem('rezzerv_token')
    setToken('')
  }

  return { token, isLoggedIn, setSession, clearSession }
}


// TABLE ROW HEIGHT DEBUG
setTimeout(()=>{
  try{
    const r=document.querySelector("tbody tr");
    if(r){console.debug("TABLE ROW HEIGHT DEBUG:", r.getBoundingClientRect().height);}
  }catch(e){}
},1000);
