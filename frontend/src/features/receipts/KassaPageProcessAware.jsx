import { useEffect } from 'react'
import KassaPage from './KassaPage.jsx'

const LOCAL_PREVIEW_CONTAINER_ID = 'rezzerv-local-receipt-preview'

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function buildImageProcessHtml(dataUrl, fileName = 'Kassabon') {
  const safeFileName = escapeHtml(fileName)
  const safeDataUrl = escapeHtml(dataUrl)
  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
body { font-family: sans-serif; background:#f8fafc; margin:0; padding:16px; }
.toolbar { display:flex; gap:12px; margin-bottom:12px; }
select { padding:8px; }
.stage-panel { display:none; }
.stage-panel.active { display:block; }
img, canvas { width:100%; }
</style>
</head>
<body>
<div class="toolbar">
<select id="step">
<option value="original">Origineel</option>
<option value="gray">Genormaliseerd</option>
<option value="th">OCR-ready</option>
</select>
<span>${safeFileName}</span>
</div>

<div id="original" class="stage-panel active"><img id="img" src="${safeDataUrl}"/></div>
<div id="gray" class="stage-panel"><canvas id="c1"></canvas></div>
<div id="th" class="stage-panel"><canvas id="c2"></canvas></div>

<script>
const img=document.getElementById('img')
const c1=document.getElementById('c1')
const c2=document.getElementById('c2')
const step=document.getElementById('step')

function show(id){
['original','gray','th'].forEach(k=>{
  document.getElementById(k).className='stage-panel'+(k===id?' active':'')
})
}

img.onload=()=>{
const w=img.naturalWidth,h=img.naturalHeight
c1.width=w;c1.height=h
c2.width=w;c2.height=h
const ctx=c1.getContext('2d')
ctx.drawImage(img,0,0)
let d=ctx.getImageData(0,0,w,h)
for(let i=0;i<d.data.length;i+=4){
 const g=(d.data[i]+d.data[i+1]+d.data[i+2])/3
 d.data[i]=d.data[i+1]=d.data[i+2]=g
}
ctx.putImageData(d,0,0)

const ctx2=c2.getContext('2d')
ctx2.putImageData(d,0,0)
let d2=ctx2.getImageData(0,0,w,h)
for(let i=0;i<d2.data.length;i+=4){
 const v=d2.data[i]>150?255:0
 d2.data[i]=d2.data[i+1]=d2.data[i+2]=v
}
ctx2.putImageData(d2,0,0)
}

step.onchange=e=>show(e.target.value)
</script>
</body>
</html>`
}

function removePreview(){
const el=document.getElementById(LOCAL_PREVIEW_CONTAINER_ID)
if(el)el.remove()
}

function insertPreview(srcdoc){
const target=document.querySelector('button')
if(!target)return false

removePreview()

const box=document.createElement('div')
box.id=LOCAL_PREVIEW_CONTAINER_ID
box.style.margin='16px 0'
box.style.padding='12px'
box.style.border='1px solid #ccc'
box.style.background='#fff'

const title=document.createElement('div')
title.textContent='Originele kassabon (direct zichtbaar)'
title.style.fontWeight='700'
title.style.marginBottom='8px'

const iframe=document.createElement('iframe')
iframe.style.width='100%'
iframe.style.height='500px'
iframe.srcdoc=srcdoc

box.appendChild(title)
box.appendChild(iframe)

target.parentElement.parentElement.appendChild(box)
return true
}

function fileToPreview(file){
return new Promise((res,rej)=>{
if(file.type.startsWith('image/')){
const r=new FileReader()
r.onload=()=>res(buildImageProcessHtml(r.result,file.name))
r.readAsDataURL(file)
}else rej()
})
}

export default function KassaPageProcessAware(){
useEffect(()=>{
const handler=async e=>{
const f=e.target.files?.[0]
if(!f)return
try{
const srcdoc=await fileToPreview(f)
insertPreview(srcdoc)
}catch{}
}

document.addEventListener('change',handler,true)
return()=>document.removeEventListener('change',handler,true)
},[])

return <KassaPage/>
}
