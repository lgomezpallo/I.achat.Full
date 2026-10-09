HTML = r"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#10151e"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="apple-mobile-web-app-title" content="IAchat"><link rel="manifest" href="/manifest.webmanifest"><link rel="icon" type="image/png" sizes="192x192" href="/icons/icon-192.png"><link rel="apple-touch-icon" href="/icons/icon-192.png">
<title>IAchat</title>
<style>
:root{color-scheme:dark;--bg:#10151e;--panel:#181f2b;--edge:#303949;--txt:#f0f3fb;--muted:#aab6cb;--accent:#759bf7;--bubble:#304363}
*{box-sizing:border-box}html,body{margin:0;height:100%;font:15px/1.5 system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--txt)}
button,textarea,input{font:inherit}button{cursor:pointer;border:0;color:inherit}
.shell{max-width:940px;margin:0 auto;height:100dvh;display:flex;flex-direction:column;position:relative}
header{height:62px;min-height:62px;display:flex;align-items:center;justify-content:space-between;padding:6px 17px;border-bottom:1px solid var(--edge)}
.brand{text-align:center}.brand strong{font-size:19px;font-weight:650;letter-spacing:.1px}.brand small{display:block;font-size:11px;color:var(--muted);line-height:15px}
.iconbtn{width:43px;height:43px;border-radius:15px;background:#222c3b;font-size:25px}
#messages{flex:1;min-height:0;overflow-y:auto;padding:18px 18px 12px;display:flex;flex-direction:column;gap:17px;scrollbar-width:thin}
.msg{max-width:88%;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.56;font-size:15px}
.user{align-self:flex-end;background:var(--bubble);border-radius:20px 20px 6px 20px;padding:12px 16px}
.assistant{align-self:flex-start;padding:4px 4px 4px 33px;position:relative}
.assistant:before{content:'✦';position:absolute;top:5px;left:0;width:24px;height:24px;border-radius:9px;background:#263851;color:#b6d1ff;display:grid;place-items:center;font-size:12px}
.error{color:#ff9da7}.waiting{color:var(--muted)}.empty{margin:auto;text-align:center;color:var(--muted);font-size:17px}
.bottom{border-top:1px solid var(--edge);background:var(--bg);padding:9px 16px max(13px,env(safe-area-inset-bottom))}
.modes{display:flex;align-items:center;gap:6px;margin-bottom:9px}
.mode{padding:9px 13px;border-radius:13px;background:transparent;color:var(--muted);font-size:13px}.mode.active{background:#283b55;color:#e3edff}
.composer{display:flex;gap:8px;align-items:flex-end;padding:8px;border:1px solid var(--edge);border-radius:22px;background:var(--panel)}
#input{flex:1;min-width:0;resize:none;min-height:39px;max-height:134px;padding:9px 5px;border:0;outline:0;background:transparent;color:var(--txt)}
#input::placeholder{color:var(--muted)}.attach{width:36px;height:38px;background:transparent;color:var(--muted);font-size:25px}
.send{width:39px;height:39px;border-radius:14px;background:var(--accent);color:#091326;font-size:23px;font-weight:700}.send:disabled{opacity:.45}
.note{text-align:center;color:#8897af;font-size:10px;margin:7px 0 0}
#drawer{position:absolute;z-index:8;top:0;bottom:0;left:0;width:min(85vw,320px);background:#1b2432;border-right:1px solid var(--edge);padding:19px;box-shadow:12px 0 60px #0008;display:none;overflow:auto}
#drawer.open{display:block}.drawer-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}
.history-item{width:100%;padding:12px;text-align:left;background:#293447;border-radius:12px;margin-bottom:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#login{position:absolute;inset:0;z-index:12;background:var(--bg);display:flex;align-items:center;justify-content:center;padding:24px}
.loginbox{width:min(100%,370px);padding:24px;background:var(--panel);border-radius:22px;border:1px solid var(--edge);display:grid;gap:14px}
.loginbox h2{margin:0;font-size:24px}.loginbox p{color:var(--muted);margin:0}
.loginbox input{border:1px solid var(--edge);background:var(--bg);color:var(--txt);padding:13px;border-radius:12px;width:100%}
.loginbox button{background:var(--accent);color:#111b2b;border-radius:12px;padding:12px;font-weight:650}
#loginError{color:#ff9da7;font-size:12px}
.hidden{display:none!important}
</style></head><body>
<div class="shell">
<header><button id="history" class="iconbtn" aria-label="Conversaciones">☰</button><div class="brand"><strong>IAchat</strong><small>Tu espacio de ideas</small></div><button id="new" class="iconbtn" aria-label="Nuevo chat">+</button></header>
<main id="messages" aria-live="polite"><div class="empty" id="empty">¿En qué te puedo ayudar?</div></main>
<div class="bottom"><nav class="modes"><button class="mode active" data-mode="chat">Chat</button><button class="mode" data-mode="image">Imagen</button><button class="mode" data-mode="document">Documento</button></nav>
<form id="form" class="composer"><button type="button" class="attach" title="Adjuntos: próximamente" aria-label="Adjuntar">+</button><textarea id="input" rows="1" placeholder="Escribí un mensaje…" required></textarea><button class="send" aria-label="Enviar">↑</button></form>
<p id="note" class="note">Revisá la información importante antes de usarla.</p></div>
<aside id="drawer"><div class="drawer-head"><strong>Conversaciones</strong><button id="close" class="iconbtn">×</button></div><button class="history-item" id="drawerNew">+ Nueva conversación</button><div id="historyList"></div><button class="history-item" id="logout">Cerrar sesión</button></aside>
<div id="login" class="hidden"><form class="loginbox" id="loginForm"><h2>IAchat</h2><p>Tu espacio privado de conversación.</p><input id="password" type="password" autocomplete="current-password" placeholder="Contraseña" required><button>Entrar</button><span id="loginError"></span></form></div>
</div>
<script>
var conversationId=null,busy=false;
var messages=document.getElementById('messages'),input=document.getElementById('input'),drawer=document.getElementById('drawer');
var ids=[];try{ids=JSON.parse(localStorage.getItem('iachat.history')||'[]');if(!Array.isArray(ids))ids=[]}catch(e){ids=[]}
function saveIds(){localStorage.setItem('iachat.history',JSON.stringify(ids.slice(0,80)))}
async function syncHistory(){var r=await fetch('/api/conversations');if(r.status===401){showLogin();return false}if(!r.ok)throw Error('No se pudo cargar el historial');var d=await r.json();ids=d.conversations||[];saveIds();renderHistory();return true}
function add(role,text,error){document.getElementById('empty')?.remove();var e=document.createElement('div');e.className='msg '+role+(error?' error':'');e.textContent=text;messages.appendChild(e);messages.scrollTop=messages.scrollHeight;return e}
function reset(){conversationId=null;messages.innerHTML='<div class="empty" id="empty">¿En qué te puedo ayudar?</div>';input.value='';drawer.classList.remove('open');}
function renderHistory(){var list=document.getElementById('historyList');list.replaceChildren();ids.forEach(function(item){var wrap=document.createElement('div');wrap.style.cssText='display:flex;align-items:center;gap:4px';var b=document.createElement('button');b.className='history-item';b.style.flex='1';b.textContent=item.title||'Conversación';b.onclick=function(){openConversation(item.id)};var del=document.createElement('button');del.textContent='×';del.title='Borrar conversación';del.setAttribute('aria-label','Borrar conversación');del.style.cssText='background:transparent;padding:10px';del.onclick=async function(){if(!confirm('¿Borrar esta conversación?'))return;var r=await fetch('/api/conversations/'+encodeURIComponent(item.id),{method:'DELETE'});if(r.ok){if(conversationId===item.id)reset();await syncHistory()}};wrap.append(b,del);list.appendChild(wrap)})}
async function openConversation(id){try{var r=await fetch('/api/conversations/'+encodeURIComponent(id));if(r.status===401){showLogin();return}if(!r.ok)throw Error('No se pudo recuperar la conversación');var d=await r.json();conversationId=id;messages.replaceChildren();if(!d.history.length)reset();else d.history.forEach(function(m){add(m.role,m.content)});drawer.classList.remove('open')}catch(e){add('assistant',String(e.message||e),true)}}
function showLogin(){document.getElementById('login').classList.remove('hidden')}
async function init(){try{var r=await fetch('/auth/status');var d=await r.json();if(!d.authenticated){showLogin();return}if(await syncHistory()&&ids.length)await openConversation(ids[0].id)}catch(e){showLogin()}}
document.getElementById('loginForm').onsubmit=async function(e){e.preventDefault();var r=await fetch('/auth/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({password:document.getElementById('password').value})});if(r.ok){document.getElementById('password').value='';document.getElementById('login').classList.add('hidden');init()}else document.getElementById('loginError').textContent='Contraseña incorrecta'};
document.getElementById('history').onclick=async function(){await syncHistory();drawer.classList.toggle('open')};
document.getElementById('close').onclick=function(){drawer.classList.remove('open')};
document.getElementById('new').onclick=reset;document.getElementById('drawerNew').onclick=reset;
document.getElementById('logout').onclick=async function(){await fetch('/auth/logout',{method:'POST'});reset();showLogin()};
document.querySelectorAll('.mode').forEach(function(b){b.onclick=function(){if(b.dataset.mode!=='chat'){document.getElementById('note').textContent='Imagen y Documento estarán disponibles más adelante.';return}document.getElementById('note').textContent='Revisá la información importante antes de usarla.'}});
document.querySelector('.attach').onclick=function(){document.getElementById('note').textContent='Los archivos adjuntos estarán disponibles más adelante.'};
document.getElementById('form').onsubmit=async function(e){e.preventDefault();if(busy)return;var text=input.value.trim();if(!text)return;busy=true;input.value='';add('user',text);var waiting=add('assistant','Pensando…');var payload={text:text};if(conversationId)payload.conversation_id=conversationId;
try{var r=await fetch('/api/chat',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)});var d=await r.json();waiting.remove();if(!r.ok){input.value=text;add('assistant',d.detail||'No se pudo enviar. Podés reintentarlo.',true);if(r.status===401)showLogin();return}conversationId=d.conversation_id;ids=ids.filter(function(x){return x.id!==conversationId});ids.unshift({id:conversationId,title:text.slice(0,55)});saveIds();syncHistory().catch(function(){});add('assistant',d.answer)}
catch(err){waiting.remove();input.value=text;add('assistant','No hay conexión. El mensaje sigue en la caja para reintentar.',true)}finally{busy=false}};
input.addEventListener('keydown',function(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();document.getElementById('form').requestSubmit()}});
init();if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js');
</script></body></html>"""

MANIFEST = {
    "id": "/", "name": "IAchat", "short_name": "IAchat",
    "description": "Tu espacio privado de conversación",
    "start_url": "/", "scope": "/", "display": "standalone",
    "background_color": "#10151e", "theme_color": "#10151e",
    "icons": [
        {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
        {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
    ]
}
SERVICE_WORKER = """const CACHE='iachat-shell-v4';
const ASSETS=['/','/manifest.webmanifest','/icons/icon-192.png','/icons/icon-512.png'];
self.addEventListener('install',event=>{
 event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)).then(()=>self.skipWaiting()));
});
self.addEventListener('activate',event=>{
 event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);
 if(event.request.method!=='GET'||url.origin!==self.location.origin)return;
 if(url.pathname.startsWith('/api/')||url.pathname.startsWith('/auth/'))return;
 if(url.pathname==='/' ){
  event.respondWith(fetch(event.request).catch(()=>caches.match('/')));
  return;
 }
 if(ASSETS.includes(url.pathname)){
  event.respondWith(caches.match(event.request).then(cached=>cached||fetch(event.request)));
 }
});"""
