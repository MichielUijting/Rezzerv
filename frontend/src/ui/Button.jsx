
export default function Button({ variant = 'primary', className = '', ...props }) {
  const cls = [
    variant === 'primary' ? 'rz-button-primary' : 'rz-button-secondary',
    className
  ].filter(Boolean).join(' ')
  return <button className={cls} {...props} />
}


// TABLE ROW HEIGHT DEBUG
setTimeout(()=>{
  try{
    const r=document.querySelector("tbody tr");
    if(r){console.debug("TABLE ROW HEIGHT DEBUG:", r.getBoundingClientRect().height);}
  }catch(e){}
},1000);
