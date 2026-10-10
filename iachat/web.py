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
.assistant p{margin:0 0 10px;white-space:pre-wrap}.assistant p:last-child{margin-bottom:0}.assistant h3,.assistant h4,.assistant h5,.assistant h6{margin:13px 0 7px;font-size:15px;line-height:1.35}.assistant ul,.assistant ol{margin:6px 0 12px;padding-left:23px}.assistant li{margin:4px 0}.assistant pre{overflow-x:auto;background:#1b2534;border:1px solid var(--edge);border-radius:9px;padding:10px;white-space:pre;font-size:13px}.assistant code{background:#273246;padding:2px 4px;border-radius:4px}.assistant pre code{background:transparent;padding:0}.assistant table{border-collapse:collapse;display:block;max-width:100%;overflow-x:auto;margin:10px 0;font-size:13px}.assistant th,.assistant td{border:1px solid var(--edge);padding:7px 9px;text-align:left;vertical-align:top}.assistant a{color:#9dbbff;text-decoration:underline}
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
<form id="form" class="composer"><button type="button" class="attach" title="Adjuntar TXT, MD o PDF" aria-label="Adjuntar">+</button><input type="file" id="attachments" accept=".txt,.md,.pdf" multiple hidden><textarea id="input" rows="1" placeholder="Escribí un mensaje…"></textarea><button class="send" aria-label="Enviar">↑</button></form>
<p id="selectedFiles" class="note"></p><p id="note" class="note">Revisá la información importante antes de usarla.</p></div>
<aside id="drawer"><div class="drawer-head"><strong>Conversaciones</strong><button id="close" class="iconbtn">×</button></div><button class="history-item" id="drawerNew">+ Nueva conversación</button><input id="historySearch" type="search" placeholder="Buscar en mis conversaciones" autocomplete="off" style="width:100%;padding:11px;margin-bottom:10px;background:var(--bg);color:var(--txt);border:1px solid var(--edge);border-radius:11px"><div id="historySearchStatus" style="font-size:12px;color:var(--muted)"></div><div id="historyList"></div><hr style="border:0;border-top:1px solid var(--edge);margin:18px 0"><strong>Memoria</strong><label for="projectScope" style="display:block;font-size:12px;margin-top:10px;color:var(--muted)">Proyecto activo (vacío = General)</label><input id="projectScope" maxlength="60" list="projectSuggestions" placeholder="General" autocomplete="off" style="width:100%;background:var(--bg);color:var(--txt);border:1px solid var(--edge);border-radius:10px;padding:9px"><datalist id="projectSuggestions"><option value="IAchat"></option><option value="Router"></option><option value="Auditor"></option></datalist><p style="color:var(--muted);font-size:12px">Datos que IAchat recordará entre conversaciones.</p><button class="history-item" id="suggestMemories" type="button">✦ Sugerir recuerdos de este chat</button><div id="memorySuggestions"></div><div id="memoryList"></div><form id="memoryForm"><textarea id="memoryInput" rows="2" maxlength="1000" placeholder="Agregar algo para recordar" style="width:100%;background:var(--bg);color:var(--txt);border:1px solid var(--edge);border-radius:10px;padding:10px" required></textarea><button class="history-item" type="submit">+ Guardar recuerdo</button></form><div id="accountAdmin" class="hidden"><hr style="border:0;border-top:1px solid var(--edge)"><strong>Administrar cuentas</strong><div id="accountList"></div><form id="accountForm"><input id="newUsername" placeholder="Nuevo usuario" minlength="3" maxlength="32" required style="width:100%;padding:10px;margin:8px 0;background:var(--bg);color:var(--txt);border:1px solid var(--edge)"><input id="newPassword" type="password" minlength="8" placeholder="Contraseña (mínimo 8 caracteres)" required style="width:100%;padding:10px;background:var(--bg);color:var(--txt);border:1px solid var(--edge)"><button class="history-item" type="submit">+ Agregar cuenta</button></form></div><button class="history-item" id="exportData" type="button">↓ Exportar mis conversaciones y memoria</button><button class="history-item" id="logout">Cerrar sesión</button></aside>
<div id="login" class="hidden"><form class="loginbox" id="loginForm"><h2>IAchat</h2><p>Tu espacio privado de conversación.</p><input id="username" autocomplete="username" value="admin" placeholder="Usuario" required><input id="password" type="password" autocomplete="current-password" placeholder="Contraseña" required><button>Entrar</button><span id="loginError"></span></form></div>
</div>
<script>
var conversationId=null,busy=false,activeUser=null;
function activeProject(){return (document.getElementById('projectScope').value||'').trim().slice(0,60)}
document.getElementById('projectScope').value=localStorage.getItem('iachat.activeProject')||'';
document.getElementById('projectScope').addEventListener('change',function(){localStorage.setItem('iachat.activeProject',activeProject())});

var messages=document.getElementById('messages'),input=document.getElementById('input'),drawer=document.getElementById('drawer');
var ids=[];try{ids=JSON.parse(localStorage.getItem('iachat.history.'+(activeUser||'admin'))||'[]');if(!Array.isArray(ids))ids=[]}catch(e){ids=[]}
function saveIds(){localStorage.setItem('iachat.history.'+(activeUser||'admin'),JSON.stringify(ids.slice(0,80)))}
async function syncHistory(){var r=await fetch('/api/conversations');if(r.status===401){showLogin();return false}if(!r.ok)throw Error('No se pudo cargar el historial');var d=await r.json();ids=d.conversations||[];saveIds();renderHistory();return true}

/* Markdown is rendered with DOM text nodes, never by injecting model HTML. */
function inlineMd(parent,value){
 var pattern=/(\*\*[^*\n]+\*\*|`[^`\n]+`|\[[^\]\n]+\]\(https?:\/\/[^\s)]+\))/g;
 var last=0,match;
 while((match=pattern.exec(value))!==null){
  if(match.index>last)parent.append(document.createTextNode(value.slice(last,match.index)));
  var token=match[0],element;
  if(token.startsWith('**')){element=document.createElement('strong');element.textContent=token.slice(2,-2)}
  else if(token.startsWith('`')){element=document.createElement('code');element.textContent=token.slice(1,-1)}
  else{
   var parts=/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/.exec(token);
   element=document.createElement('a');element.textContent=parts[1];element.href=parts[2];
   element.target='_blank';element.rel='noopener noreferrer';
  }
  parent.append(element);last=pattern.lastIndex;
 }
 if(last<value.length)parent.append(document.createTextNode(value.slice(last)));
}
function renderMarkdown(target,value){
 var lines=String(value||'').replace(/\r\n?/g,'\n').split('\n'),index=0;
 var isTableRow=line=>/^\s*\|.*\|\s*$/.test(line);
 var isSeparator=line=>/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
 var cells=line=>line.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(x=>x.trim());
 var isList=line=>/^\s*([-*]|\d+\.)\s+/.test(line);
 while(index<lines.length){
  var line=lines[index];
  if(!line.trim()){index++;continue}
  if(line.trim().startsWith('```')){
   var language=line.trim().slice(3).trim(),code=[];
   index++;while(index<lines.length&&!lines[index].trim().startsWith('```'))code.push(lines[index++]);
   if(index<lines.length)index++;
   var pre=document.createElement('pre'),el=document.createElement('code');
   el.textContent=code.join('\n');pre.append(el);target.append(pre);continue;
  }
  if(isTableRow(line)&&index+1<lines.length&&isSeparator(lines[index+1])){
   var table=document.createElement('table'),head=document.createElement('thead'),row=document.createElement('tr');
   cells(line).forEach(value=>{var th=document.createElement('th');inlineMd(th,value);row.append(th)});
   head.append(row);table.append(head);index+=2;var body=document.createElement('tbody');
   while(index<lines.length&&isTableRow(lines[index])){
    var tr=document.createElement('tr');cells(lines[index]).forEach(value=>{var td=document.createElement('td');inlineMd(td,value);tr.append(td)});
    body.append(tr);index++;
   }
   table.append(body);target.append(table);continue;
  }
  var heading=/^\s*(#{1,4})\s+(.+)$/.exec(line);
  if(heading){var h=document.createElement('h'+Math.min(heading[1].length+2,6));inlineMd(h,heading[2]);target.append(h);index++;continue}
  if(isList(line)){
   var ordered=/^\s*\d+\.\s+/.test(line),list=document.createElement(ordered?'ol':'ul');
   while(index<lines.length&&isList(lines[index])===true&&(/^\s*\d+\.\s+/.test(lines[index]))===ordered){
    var li=document.createElement('li');inlineMd(li,lines[index].replace(/^\s*([-*]|\d+\.)\s+/,''));list.append(li);index++;
   }
   target.append(list);continue;
  }
  var paragraph=document.createElement('p'),parts=[line];index++;
  while(index<lines.length&&lines[index].trim()&&!/^\s*#{1,4}\s/.test(lines[index])&&!isList(lines[index])&&!lines[index].trim().startsWith('```')&&!(isTableRow(lines[index])&&index+1<lines.length&&isSeparator(lines[index+1]))){parts.push(lines[index++])}
  inlineMd(paragraph,parts.join('\n'));target.append(paragraph);
 }
}

function add(role,text,error){document.getElementById('empty')?.remove();var e=document.createElement('div');e.className='msg '+role+(error?' error':'');if(role==='assistant'&&!error)renderMarkdown(e,text);else e.textContent=text;messages.appendChild(e);messages.scrollTop=messages.scrollHeight;return e}
function reset(){conversationId=null;messages.innerHTML='<div class="empty" id="empty">¿En qué te puedo ayudar?</div>';input.value='';drawer.classList.remove('open');}
function renderHistory(){var list=document.getElementById('historyList');list.replaceChildren();ids.forEach(function(item){var wrap=document.createElement('div');wrap.style.cssText='display:flex;align-items:center;gap:4px';var b=document.createElement('button');b.className='history-item';b.style.flex='1';b.textContent=item.title||'Conversación';b.onclick=function(){openConversation(item.id)};var del=document.createElement('button');del.textContent='×';del.title='Borrar conversación';del.setAttribute('aria-label','Borrar conversación');del.style.cssText='background:transparent;padding:10px';del.onclick=async function(){if(!confirm('¿Borrar esta conversación?'))return;var r=await fetch('/api/conversations/'+encodeURIComponent(item.id),{method:'DELETE'});if(r.ok){if(conversationId===item.id)reset();await syncHistory()}};wrap.append(b,del);list.appendChild(wrap)})}
var searchTimer, searchSequence=0;
document.getElementById('historySearch').addEventListener('input',function(){
 var term=this.value.trim(), sequence=++searchSequence;
 clearTimeout(searchTimer);
 if(term.length<2){document.getElementById('historySearchStatus').textContent='';renderHistory();return}
 document.getElementById('historySearchStatus').textContent='Buscando…';
 searchTimer=setTimeout(async function(){
  try{
   var response=await fetch('/api/conversations/search?q='+encodeURIComponent(term));
   if(!response.ok)throw Error('Error al buscar');
   var data=await response.json(), matches=data.matches||[];
   if(sequence!==searchSequence)return;
   var list=document.getElementById('historyList');list.replaceChildren();
   matches.forEach(function(item){var b=document.createElement('button');b.className='history-item';b.style.whiteSpace='normal';b.textContent=(item.title||'Conversación')+' · '+(item.excerpt||'');b.onclick=function(){openConversation(item.id)};list.appendChild(b)});
   document.getElementById('historySearchStatus').textContent=matches.length?(matches.length+' coincidencia'+(matches.length===1?'':'s')):'Sin resultados para esa búsqueda';
  }catch(e){if(sequence===searchSequence)document.getElementById('historySearchStatus').textContent='No se pudo buscar'}
 },280);
});
async function openConversation(id){try{var r=await fetch('/api/conversations/'+encodeURIComponent(id));if(r.status===401){showLogin();return}if(!r.ok)throw Error('No se pudo recuperar la conversación');var d=await r.json();conversationId=id;messages.replaceChildren();if(!d.history.length)reset();else d.history.forEach(function(m){add(m.role,m.content)});drawer.classList.remove('open')}catch(e){add('assistant',String(e.message||e),true)}}
async function syncMemories(){var r=await fetch('/api/memories');if(!r.ok)return;var d=await r.json();var box=document.getElementById('memoryList');box.replaceChildren();if(!d.memories.length){var empty=document.createElement('p');empty.textContent='Todavía no hay recuerdos guardados.';empty.style.cssText='color:var(--muted);font-size:13px';box.append(empty)}d.memories.forEach(function(item){var el=document.createElement('div');el.style.cssText='padding:8px 0;border-bottom:1px solid var(--edge)';var txt=document.createElement('div');txt.textContent=(item.project?'['+item.project+'] ':'[General] ')+item.content;txt.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px';var controls=document.createElement('div');controls.style.cssText='display:flex;gap:8px';var edit=document.createElement('button');edit.textContent='Editar';edit.style.cssText='background:transparent;color:var(--accent)';edit.onclick=async function(){var value=prompt('Editar recuerdo',item.content);if(value===null||!value.trim())return;var q=await fetch('/api/memories/'+encodeURIComponent(item.id),{method:'PUT',headers:{'content-type':'application/json'},body:JSON.stringify({content:value.trim(),project:item.project||''})});if(q.ok)syncMemories()};var del=document.createElement('button');del.textContent='Borrar';del.style.cssText='background:transparent;color:#ff9da7';del.onclick=async function(){if(!confirm('¿Eliminar este recuerdo?'))return;var q=await fetch('/api/memories/'+encodeURIComponent(item.id),{method:'DELETE'});if(q.ok)syncMemories()};var move=document.createElement('button');move.textContent='Proyecto';move.title='Cambiar proyecto del recuerdo';move.style.cssText='background:transparent;color:var(--accent)';move.onclick=async function(){var value=prompt('Proyecto del recuerdo (dejá vacío para General)',item.project||'');if(value===null)return;value=value.trim();if(value.length>60||!/^[\p{L}\p{N}_ -]*$/u.test(value)){alert('Usá un nombre de hasta 60 caracteres, sin símbolos especiales.');return}var q=await fetch('/api/memories/'+encodeURIComponent(item.id),{method:'PUT',headers:{'content-type':'application/json'},body:JSON.stringify({content:item.content,project:value})});if(q.ok)syncMemories();else alert('No se pudo cambiar el proyecto')};controls.append(edit,move,del);el.append(txt,controls);box.append(el)})}
document.getElementById('memoryForm').onsubmit=async function(e){e.preventDefault();var field=document.getElementById('memoryInput');var val=field.value.trim();if(!val)return;var r=await fetch('/api/memories',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({content:val,project:activeProject()})});if(r.ok){field.value='';await syncMemories()}else alert('No se pudo guardar el recuerdo')};
document.getElementById('suggestMemories').onclick=async function(){var box=document.getElementById('memorySuggestions');box.replaceChildren();if(!conversationId){box.textContent='Primero abrí una conversación.';return}box.textContent='Analizando conversación mediante Router…';try{var r=await fetch('/api/memories/suggest',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({conversation_id:conversationId,project:activeProject()})});if(!r.ok)throw Error('No se pudieron generar sugerencias');var data=await r.json();box.replaceChildren();if(!data.suggestions.length){box.textContent='No encontré nuevos recuerdos para proponer.';return}data.suggestions.forEach(function(item){var wrap=document.createElement('div');wrap.style.cssText='padding:9px;border:1px solid var(--edge);border-radius:10px;margin-bottom:8px';var ta=document.createElement('textarea');ta.value=item;ta.maxLength=250;ta.rows=3;ta.style.cssText='width:100%;background:var(--bg);color:var(--txt);border:1px solid var(--edge);border-radius:8px;padding:6px';var save=document.createElement('button');save.textContent='Guardar recuerdo';save.className='history-item';save.onclick=async function(){var content=ta.value.trim();if(!content)return;var result=await fetch('/api/memories',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({content:content,project:activeProject()})});if(result.ok){wrap.remove();syncMemories()}else alert('No se pudo guardar')};var dismiss=document.createElement('button');dismiss.textContent='Descartar';dismiss.style.cssText='background:transparent;color:var(--muted)';dismiss.onclick=function(){wrap.remove()};wrap.append(ta,save,dismiss);box.append(wrap)})}catch(e){box.textContent=e.message||'Error de sugerencias'}};
function showLogin(){document.getElementById('login').classList.remove('hidden')}
async function init(){try{var r=await fetch('/auth/status');var d=await r.json();if(!d.authenticated){showLogin();return}activeUser=d.username;ids=[];document.getElementById('accountAdmin').classList.toggle('hidden',!d.admin);if(d.admin)await loadAccounts();if(await syncHistory()&&ids.length)await openConversation(ids[0].id);await syncMemories()}catch(e){showLogin()}}
document.getElementById('loginForm').onsubmit=async function(e){e.preventDefault();var r=await fetch('/auth/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username:document.getElementById('username').value,password:document.getElementById('password').value})});if(r.ok){document.getElementById('password').value='';document.getElementById('login').classList.add('hidden');init()}else document.getElementById('loginError').textContent='Contraseña incorrecta'};
document.getElementById('history').onclick=async function(){await syncHistory();await syncMemories();drawer.classList.toggle('open')};
document.getElementById('close').onclick=function(){drawer.classList.remove('open')};
document.getElementById('new').onclick=reset;document.getElementById('drawerNew').onclick=reset;
document.getElementById('exportData').onclick=async function(){
 try{
  var r=await fetch('/api/export',{cache:'no-store'});
  if(!r.ok)throw Error('No se pudo exportar');
  var blob=await r.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=url;link.download='iachat-export-'+new Date().toISOString().slice(0,10)+'.json';
  document.body.appendChild(link);link.click();link.remove();setTimeout(function(){URL.revokeObjectURL(url)},5000);
 }catch(e){alert(e.message||'Error al exportar')}
};
document.getElementById('logout').onclick=async function(){await fetch('/auth/logout',{method:'POST'});reset();ids=[];activeUser=null;showLogin()};
async function loadAccounts(){var r=await fetch('/api/users');if(!r.ok)return;var data=await r.json();var box=document.getElementById('accountList');box.replaceChildren();data.users.forEach(function(u){var b=document.createElement('button');b.className='history-item';b.textContent=u.username+(u.admin?' (administrador)':'')+' — '+(u.enabled?'Activa':'Desactivada');if(!u.admin)b.onclick=async function(){if(!confirm((u.enabled?'Desactivar ':'Activar ')+u.username+'?'))return;await fetch('/api/users/'+encodeURIComponent(u.username)+'/enabled?enabled='+(!u.enabled),{method:'PUT'});loadAccounts()};else b.disabled=true;box.append(b)})}
document.getElementById('accountForm').onsubmit=async function(e){e.preventDefault();var username=document.getElementById('newUsername').value.trim(),password=document.getElementById('newPassword').value;var r=await fetch('/api/users',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username:username,password:password})});if(r.ok){this.reset();loadAccounts();alert('Cuenta creada')}else{var d=await r.json();alert(d.detail||'No se pudo crear la cuenta')}};
document.querySelectorAll('.mode').forEach(function(b){b.onclick=function(){if(b.dataset.mode!=='chat'){document.getElementById('note').textContent='Imagen y Documento estarán disponibles más adelante.';return}document.getElementById('note').textContent='Revisá la información importante antes de usarla.'}});
var fileInput=document.getElementById('attachments');
document.querySelector('.attach').onclick=function(){fileInput.click()};
fileInput.onchange=function(){var fs=[...fileInput.files];document.getElementById('selectedFiles').textContent=fs.length?fs.map(f=>f.name).join(', '):''};
function fileBase64(f){return new Promise(function(resolve,reject){var rd=new FileReader();rd.onload=function(){resolve(String(rd.result).split(',')[1])};rd.onerror=reject;rd.readAsDataURL(f)})}

document.getElementById('form').onsubmit=async function(e){e.preventDefault();if(busy)return;var text=input.value.trim(),files=[...fileInput.files];if(!text&&!files.length)return;if(files.length>3){alert('Podés adjuntar como máximo 3 archivos.');return}
var oversized=files.find(f=>f.size>2000000);
if(oversized){alert('El archivo "'+oversized.name+'" pesa '+(oversized.size/1000000).toFixed(2)+' MB. El máximo es 2 MB por archivo.');return}
var invalid=files.find(f=>!['.txt','.md','.pdf'].some(ext=>f.name.toLowerCase().endsWith(ext)));
if(invalid){alert('El archivo "'+invalid.name+'" no es TXT, MD ni PDF.');return}
busy=true;input.value='';add('user',text+(files.length?'\nAdjuntos: '+files.map(f=>f.name).join(', '):''));var waiting=add('assistant','Pensando…');var payload={text:text,project:activeProject()};if(conversationId)payload.conversation_id=conversationId;
try{payload.attachments=await Promise.all(files.map(async function(f){return {name:f.name,content_base64:await fileBase64(f)}}));var r=await fetch('/api/chat',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)});var d=await r.json();waiting.remove();if(!r.ok){input.value=text;add('assistant',d.detail||'No se pudo enviar. Podés reintentarlo.',true);if(r.status===401)showLogin();return}fileInput.value='';document.getElementById('selectedFiles').textContent='';conversationId=d.conversation_id;ids=ids.filter(function(x){return x.id!==conversationId});ids.unshift({id:conversationId,title:text.slice(0,55)});saveIds();syncHistory().catch(function(){});add('assistant',d.answer)}
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
SERVICE_WORKER = """const CACHE='iachat-shell-v10';
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
