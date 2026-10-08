HTML = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#111827">
<link rel="manifest" href="/manifest.webmanifest">
<title>IAchat</title>
<style>
*{box-sizing:border-box}body{margin:0;font-family:system-ui;background:#0b1020;color:#e5e7eb}
main{max-width:820px;height:100dvh;margin:auto;display:grid;grid-template-rows:auto 1fr auto}
header{padding:16px 18px;border-bottom:1px solid #253047;font-weight:700}
#messages{overflow:auto;padding:20px;display:flex;flex-direction:column;gap:12px}
.msg{max-width:85%;padding:11px 13px;border-radius:15px;white-space:pre-wrap;line-height:1.4}
.user{align-self:flex-end;background:#334155}.assistant{align-self:flex-start;background:#182235}
form{display:flex;gap:8px;padding:12px;border-top:1px solid #253047;background:#0b1020}
textarea{flex:1;resize:none;border:1px solid #334155;border-radius:12px;padding:12px;background:#111827;color:white;min-height:48px;max-height:140px}
button{border:0;border-radius:12px;padding:0 18px;font-weight:700;cursor:pointer}
small{opacity:.65;font-weight:400}
</style></head>
<body><main><header>IAchat <small>· Router desacoplado</small></header>
<section id="messages"></section>
<form id="form"><textarea id="input" rows="1" placeholder="Escribí un mensaje…" required></textarea><button>Enviar</button></form>
</main>
<script>
let conversationId=localStorage.getItem("iachat.conversation");
const messages=document.getElementById("messages"), input=document.getElementById("input"), form=document.getElementById("form");
function add(role,text){const e=document.createElement("div");e.className="msg "+role;e.textContent=text;messages.appendChild(e);messages.scrollTop=messages.scrollHeight}
async function restore(){if(!conversationId)return;const r=await fetch("/api/conversations/"+conversationId);if(!r.ok){localStorage.removeItem("iachat.conversation");conversationId=null;return}const d=await r.json();for(const m of d.history)add(m.role,m.content)}
form.addEventListener("submit",async e=>{e.preventDefault();const text=input.value.trim();if(!text)return;input.value="";add("user",text);const payload={text};if(conversationId)payload.conversation_id=conversationId;try{const r=await fetch("/api/chat",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok){input.value=text;add("assistant","No se pudo enviar el mensaje ("+(d.detail||"error de servidor")+"). Podés reintentarlo.");return}conversationId=d.conversation_id;localStorage.setItem("iachat.conversation",conversationId);add("assistant",d.answer)}catch(err){input.value=text;add("assistant","No hay conexión con IAchat. El mensaje sigue disponible para reintentar.")}});
restore(); if("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
</script></body></html>"""

MANIFEST = {
    "name": "IAchat",
    "short_name": "IAchat",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#0b1020",
    "theme_color": "#111827",
}

SERVICE_WORKER = """const CACHE='iachat-v1';self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(['/','/manifest.webmanifest']))));self.addEventListener('fetch',e=>{if(e.request.method==='GET')e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)))})"""
