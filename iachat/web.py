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
.user{align-self:flex-end;background:var(--bubble);border-radius:20px 20px 6px 20px;padding:12px 16px}.sent-image{display:block;max-width:100%;width:auto;max-height:260px;border-radius:12px;margin-top:8px;object-fit:contain}.sent-file{font-size:12px;color:#d1ddf3;margin-top:6px}
.assistant{align-self:flex-start;padding:4px 4px 4px 33px;position:relative}
.assistant:before{content:'✦';position:absolute;top:5px;left:0;width:24px;height:24px;border-radius:9px;background:#263851;color:#b6d1ff;display:grid;place-items:center;font-size:12px}
.assistant p{margin:0 0 10px;white-space:pre-wrap}.assistant p:last-child{margin-bottom:0}.assistant h3,.assistant h4,.assistant h5,.assistant h6{margin:13px 0 7px;font-size:15px;line-height:1.35}.assistant ul,.assistant ol{margin:6px 0 12px;padding-left:23px}.assistant li{margin:4px 0}.assistant pre{overflow-x:auto;background:#1b2534;border:1px solid var(--edge);border-radius:9px;padding:10px;white-space:pre;font-size:13px}.assistant code{background:#273246;padding:2px 4px;border-radius:4px}.assistant pre code{background:transparent;padding:0}.assistant table{border-collapse:collapse;display:block;max-width:100%;overflow-x:auto;margin:10px 0;font-size:13px}.assistant th,.assistant td{border:1px solid var(--edge);padding:7px 9px;text-align:left;vertical-align:top;min-width:145px;overflow-wrap:normal;word-break:normal}.assistant a{color:#9dbbff;text-decoration:underline}
.response-meta{display:block;margin-top:7px;color:var(--muted);font-size:11px;line-height:1.4;opacity:.85;font-variant-numeric:tabular-nums}.error{color:#ff9da7}.waiting{color:var(--muted)}.empty{margin:auto;text-align:center;color:var(--muted);font-size:17px}
.bottom{border-top:1px solid var(--edge);background:var(--bg);padding:9px 16px max(13px,env(safe-area-inset-bottom))}
.composer{display:flex;gap:8px;align-items:flex-end;padding:8px;border:1px solid var(--edge);border-radius:22px;background:var(--panel)}
.attachment-menu{margin:0 0 8px;padding:6px;background:var(--panel);border:1px solid var(--edge);border-radius:15px;max-width:270px;box-shadow:0 6px 20px #0004}.attachment-menu[hidden]{display:none}.attachment-menu button{display:flex;align-items:center;gap:9px;width:100%;padding:12px;text-align:left;background:transparent;border-radius:10px}.attachment-menu button:hover,.attachment-menu button:focus-visible{background:#29374b;outline:2px solid var(--accent)}.attachment-menu span{color:var(--muted);font-size:12px;margin-left:auto}.attach[aria-expanded="true"]{background:#354d72}
#input{flex:1;min-width:0;resize:none;min-height:39px;max-height:134px;padding:9px 5px;border:0;outline:0;background:transparent;color:var(--txt)}
#input::placeholder{color:var(--muted)}.attach{min-width:42px;height:39px;padding:0 9px;border:1px solid var(--edge);border-radius:13px;background:#29374b;color:#e3edff;display:flex;align-items:center;justify-content:center;gap:6px;font-size:13px;font-weight:600;flex-shrink:0}
.attach:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.attach-icon{font-size:21px;line-height:1}
@media(max-width:380px){.attach-label{display:none}.attach{width:42px;padding:0}}
.send{width:39px;height:39px;border-radius:14px;background:var(--accent);color:#091326;font-size:23px;font-weight:700}.send:disabled{opacity:.45}
.selected-file{display:inline-flex;align-items:center;gap:5px;margin:3px;padding:4px 7px;border:1px solid var(--edge);border-radius:10px;background:var(--panel);max-width:100%}.selected-file button{background:#35445c;border-radius:8px;padding:0 7px;font-size:17px}.selected-file span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.note{text-align:center;color:#8897af;font-size:10px;margin:7px 0 0}
#drawer,#settingsDrawer{position:absolute;z-index:8;top:0;bottom:0;left:0;width:min(85vw,320px);background:#1b2432;border-right:1px solid var(--edge);padding:19px;box-shadow:12px 0 60px #0008;display:none;overflow:auto}
#drawer.open,#settingsDrawer.open{display:block}.drawer-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}
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
<header><button id="history" class="iconbtn" aria-label="Conversaciones">☰</button><div class="brand"><strong>IAchat</strong><small>Tu espacio de ideas</small></div><button id="settings" class="iconbtn" aria-label="Opciones" title="Opciones">⚙</button><button id="new" class="iconbtn" aria-label="Nuevo chat">+</button></header>
<main id="messages" aria-live="polite"><div class="empty" id="empty">¿En qué te puedo ayudar?</div></main>
<div class="bottom">
<div class="attachment-menu" id="attachmentMenu" hidden><button type="button" id="pickImages">🖼️ Imagen <span>JPG, PNG o WebP</span></button><button type="button" id="takePhoto">📷 Cámara <span>Sacar una foto</span></button><button type="button" id="pickDocuments">📄 Documento <span>PDF, TXT o MD</span></button><button type="button" id="composeFile">✦ Crear archivo <span>TXT, MD, CSV, JSON, HTML, PDF, Word, Excel</span></button></div>
<form id="form" class="composer"><button type="button" class="attach" aria-expanded="false" aria-controls="attachmentMenu" title="Adjuntar imagen o documento" aria-label="Abrir menú de adjuntos"><span class="attach-icon" aria-hidden="true">+</span></button><input type="file" id="attachments" accept=".txt,.md,.pdf" multiple hidden><input type="file" id="imageAttachments" accept="image/jpeg,image/png,image/webp" multiple hidden><input type="file" id="cameraAttachment" accept="image/*" capture="environment" hidden><textarea id="input" rows="1" placeholder="Escribí un mensaje…"></textarea><button class="send" aria-label="Enviar">↑</button></form>
<p id="selectedFiles" class="note"></p><p id="note" class="note">Revisá la información importante antes de usarla.</p></div>
<aside id="drawer"><div class="drawer-head"><strong>Conversaciones</strong><button id="close" class="iconbtn">×</button></div><button class="history-item" id="drawerNew">+ Nueva conversación</button><input id="historySearch" type="search" placeholder="Buscar en mis conversaciones" autocomplete="off" style="width:100%;padding:11px;margin-bottom:10px;background:var(--bg);color:var(--txt);border:1px solid var(--edge);border-radius:11px"><div id="historySearchStatus" style="font-size:12px;color:var(--muted)"></div><div id="historyList"></div></aside><aside id="settingsDrawer" aria-label="Opciones"><div class="drawer-head"><strong>Opciones</strong><button id="closeSettings" class="iconbtn" aria-label="Cerrar opciones">×</button></div><strong>Memoria</strong><label for="projectScope" style="display:block;font-size:12px;margin-top:10px;color:var(--muted)">Proyecto activo (vacío = General)</label><input id="projectScope" maxlength="60" list="projectSuggestions" placeholder="General" autocomplete="off" style="width:100%;background:var(--bg);color:var(--txt);border:1px solid var(--edge);border-radius:10px;padding:9px"><datalist id="projectSuggestions"></datalist><p style="color:var(--muted);font-size:12px">Datos que IAchat recordará entre conversaciones.</p><button class="history-item" id="suggestMemories" type="button">✦ Sugerir recuerdos de este chat</button><div id="memorySuggestions"></div><div id="memoryList"></div><button type="button" class="history-item" id="showAutoMemories">Ver recuerdos automáticos recientes</button><div id="autoMemoryLog"></div><form id="memoryForm"><textarea id="memoryInput" rows="2" maxlength="1000" placeholder="Agregar algo para recordar" style="width:100%;background:var(--bg);color:var(--txt);border:1px solid var(--edge);border-radius:10px;padding:10px" required></textarea><button class="history-item" type="submit">+ Guardar recuerdo</button></form><div id="accountAdmin" class="hidden"><hr style="border:0;border-top:1px solid var(--edge)"><strong>Administrar cuentas</strong><div id="accountList"></div><form id="accountForm"><input id="newUsername" placeholder="Nuevo usuario" minlength="3" maxlength="32" required style="width:100%;padding:10px;margin:8px 0;background:var(--bg);color:var(--txt);border:1px solid var(--edge)"><input id="newPassword" type="password" minlength="8" placeholder="Contraseña (mínimo 8 caracteres)" required style="width:100%;padding:10px;background:var(--bg);color:var(--txt);border:1px solid var(--edge)"><button class="history-item" type="submit">+ Agregar cuenta</button></form></div><hr style="border:0;border-top:1px solid var(--edge)"><strong>Mis archivos</strong><p style="font-size:12px;color:var(--muted)">Archivos descargables creados o editados con IAchat.</p><button type="button" class="history-item" id="newWorkspaceFile">+ Crear archivo con IA</button><div id="workspaceFiles"></div><button class="history-item" id="exportData" type="button">↓ Exportar mis conversaciones y memoria</button><button class="history-item" id="logout">Cerrar sesión</button></aside>
<div id="login" class="hidden"><form class="loginbox" id="loginForm"><h2>IAchat</h2><p>Tu espacio privado de conversación.</p><input id="username" autocomplete="username" value="admin" placeholder="Usuario" required><input id="password" type="password" autocomplete="current-password" placeholder="Contraseña" required><button>Entrar</button><span id="loginError"></span></form></div>
</div>
<script>
var conversationId=null,busy=false,activeUser=null;
var fileMode=false,editFileId=null;
function chooseFileMode(id){fileMode=true;editFileId=id||null;input.placeholder=id?"Indicá cómo modificar el archivo…":"Describí el archivo que querés crear…";document.getElementById("note").textContent=id?"Modo edición de archivo":"Modo creación de archivo (TXT, MD, CSV, JSON, HTML, PDF, DOCX, XLSX)";settingsDrawer.classList.remove("open");input.focus()}
function clearFileMode(){fileMode=false;editFileId=null;input.placeholder="Escribí un mensaje…";document.getElementById("note").textContent="Revisá la información importante antes de usarla."}
function activeProject(){return (document.getElementById('projectScope').value||'').trim().slice(0,60)}
document.getElementById('projectScope').value=localStorage.getItem('iachat.activeProject')||'';
document.getElementById('projectScope').addEventListener('change',function(){localStorage.setItem('iachat.activeProject',activeProject());reset();document.getElementById('historySearch').value='';document.getElementById('historySearchStatus').textContent='';syncHistory().catch(function(){});});

var messages=document.getElementById('messages'),input=document.getElementById('input'),drawer=document.getElementById('drawer'),settingsDrawer=document.getElementById('settingsDrawer');
var ids=[];try{ids=JSON.parse(localStorage.getItem('iachat.history.'+(activeUser||'admin'))||'[]');if(!Array.isArray(ids))ids=[]}catch(e){ids=[]}
function saveIds(){localStorage.setItem('iachat.history.'+(activeUser||'admin'),JSON.stringify(ids.slice(0,80)))}
async function syncHistory(){var r=await fetch('/api/conversations?project='+encodeURIComponent(activeProject()));if(r.status===401){showLogin();return false}if(!r.ok)throw Error('No se pudo cargar el historial');var d=await r.json();ids=d.conversations||[];saveIds();renderHistory();return true}

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
function addResponseTiming(node,elapsedMs,completedAt){
  var meta=document.createElement('small');meta.className='response-meta';
  var clock=new Intl.DateTimeFormat('es-AR',{timeZone:'America/Argentina/Buenos_Aires',hour:'2-digit',minute:'2-digit',hour12:false}).format(completedAt);
  meta.textContent=clock+' · '+(elapsedMs/1000).toFixed(1).replace('.',',')+' s';
  node.appendChild(meta);
}
function reset(){clearFileMode();conversationId=null;messages.innerHTML='<div class="empty" id="empty">¿En qué te puedo ayudar?</div>';input.value='';drawer.classList.remove('open');settingsDrawer.classList.remove('open');}
function renderHistory(){var list=document.getElementById('historyList');list.replaceChildren();ids.forEach(function(item){var wrap=document.createElement('div');wrap.style.cssText='display:flex;align-items:center;gap:4px';var b=document.createElement('button');b.className='history-item';b.style.flex='1';b.textContent=item.title||'Conversación';b.onclick=function(){openConversation(item.id)};var del=document.createElement('button');del.textContent='×';del.title='Borrar conversación';del.setAttribute('aria-label','Borrar conversación');del.style.cssText='background:transparent;padding:10px';del.onclick=async function(){if(!confirm('¿Borrar esta conversación?'))return;var r=await fetch('/api/conversations/'+encodeURIComponent(item.id),{method:'DELETE'});if(r.ok){if(conversationId===item.id)reset();await syncHistory()}};var move=document.createElement('button');move.textContent='⇄';move.title='Mover conversación a otro proyecto';move.setAttribute('aria-label','Mover conversación');move.style.cssText='background:transparent;padding:10px';move.onclick=async function(){var value=prompt('Mover a proyecto (vacío = General)',item.project||'');if(value===null)return;value=value.trim();if(value.length>60||!/^[\p{L}\p{N}_ -]*$/u.test(value)){alert('Nombre de proyecto no válido');return}var resp=await fetch('/api/conversations/'+encodeURIComponent(item.id)+'/project',{method:'PUT',headers:{'content-type':'application/json'},body:JSON.stringify({project:value})});if(resp.ok){if(conversationId===item.id)reset();await syncHistory()}else alert('No se pudo mover la conversación')};wrap.append(b,move,del);list.appendChild(wrap)})}
var searchTimer, searchSequence=0;
document.getElementById('historySearch').addEventListener('input',function(){
 var term=this.value.trim(), sequence=++searchSequence;
 clearTimeout(searchTimer);
 if(term.length<2){document.getElementById('historySearchStatus').textContent='';renderHistory();return}
 document.getElementById('historySearchStatus').textContent='Buscando…';
 searchTimer=setTimeout(async function(){
  try{
   var response=await fetch('/api/conversations/search?q='+encodeURIComponent(term)+'&project='+encodeURIComponent(activeProject()));
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
document.getElementById('showAutoMemories').onclick=async function(){
 var box=document.getElementById('autoMemoryLog');box.replaceChildren();
 try{
  var response=await fetch('/api/memories/automatic-log');
  if(!response.ok)throw Error('No se pudo cargar el registro');
  var events=(await response.json()).events||[];
  if(!events.length){box.textContent='Todavía no hay recuerdos automáticos.';return}
  events.forEach(function(event){
   var item=document.createElement('div');item.style.cssText='padding:8px 0;border-bottom:1px solid var(--edge);font-size:13px';
   var desc=document.createElement('div');desc.textContent=(event.project?'['+event.project+'] ':'[General] ')+event.content+(event.undone?' (deshecho)':'');
   item.append(desc);
   if(!event.undone){
    var undo=document.createElement('button');undo.type='button';undo.textContent='Deshacer';undo.style.cssText='background:transparent;color:var(--accent);padding:7px 0';
    undo.onclick=async function(){
     var result=await fetch('/api/memories/automatic-log/'+encodeURIComponent(event.id)+'/undo',{method:'POST'});
     if(result.ok){await syncMemories();document.getElementById('showAutoMemories').click()}
     else alert('Este recuerdo fue modificado o ya no existe. No se borró nada.');
    };
    item.append(undo)
   }
   box.append(item)
  })
 }catch(e){box.textContent=e.message||'Error al cargar el registro'}
};
document.getElementById('memoryForm').onsubmit=async function(e){e.preventDefault();var field=document.getElementById('memoryInput');var val=field.value.trim();if(!val)return;var r=await fetch('/api/memories',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({content:val,project:activeProject()})});if(r.ok){field.value='';await syncMemories()}else alert('No se pudo guardar el recuerdo')};
document.getElementById('suggestMemories').onclick=async function(){var box=document.getElementById('memorySuggestions');box.replaceChildren();if(!conversationId){box.textContent='Primero abrí una conversación.';return}box.textContent='Analizando conversación mediante Router…';try{var r=await fetch('/api/memories/suggest',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({conversation_id:conversationId,project:activeProject()})});if(!r.ok)throw Error('No se pudieron generar sugerencias');var data=await r.json();box.replaceChildren();if(!data.suggestions.length){box.textContent='No encontré nuevos recuerdos para proponer.';return}data.suggestions.forEach(function(item){var wrap=document.createElement('div');wrap.style.cssText='padding:9px;border:1px solid var(--edge);border-radius:10px;margin-bottom:8px';var ta=document.createElement('textarea');ta.value=item;ta.maxLength=250;ta.rows=3;ta.style.cssText='width:100%;background:var(--bg);color:var(--txt);border:1px solid var(--edge);border-radius:8px;padding:6px';var save=document.createElement('button');save.textContent='Guardar recuerdo';save.className='history-item';save.onclick=async function(){var content=ta.value.trim();if(!content)return;var result=await fetch('/api/memories',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({content:content,project:activeProject()})});if(result.ok){wrap.remove();syncMemories()}else alert('No se pudo guardar')};var dismiss=document.createElement('button');dismiss.textContent='Descartar';dismiss.style.cssText='background:transparent;color:var(--muted)';dismiss.onclick=function(){wrap.remove()};wrap.append(ta,save,dismiss);box.append(wrap)})}catch(e){box.textContent=e.message||'Error de sugerencias'}};
function showLogin(){document.getElementById('login').classList.remove('hidden')}
async function init(){try{var r=await fetch('/auth/status');var d=await r.json();if(!d.authenticated){showLogin();return}activeUser=d.username;ids=[];document.getElementById('accountAdmin').classList.toggle('hidden',!d.admin);if(d.admin)await loadAccounts();if(await syncHistory()&&ids.length)await openConversation(ids[0].id);await syncMemories()}catch(e){showLogin()}}
document.getElementById('loginForm').onsubmit=async function(e){e.preventDefault();var r=await fetch('/auth/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username:document.getElementById('username').value,password:document.getElementById('password').value})});if(r.ok){document.getElementById('password').value='';document.getElementById('login').classList.add('hidden');init()}else document.getElementById('loginError').textContent='Contraseña incorrecta'};
document.getElementById('history').onclick=async function(){settingsDrawer.classList.remove('open');await syncHistory();drawer.classList.toggle('open')};
document.getElementById('settings').onclick=async function(){drawer.classList.remove('open');await syncMemories();await syncWorkspaceFiles();settingsDrawer.classList.toggle('open')};
document.getElementById('closeSettings').onclick=function(){settingsDrawer.classList.remove('open')};
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
var fileInput=document.getElementById('attachments'),imageInput=document.getElementById('imageAttachments'),cameraInput=document.getElementById('cameraAttachment');
var attachButton=document.querySelector('.attach'),attachMenu=document.getElementById('attachmentMenu');
function closeAttachmentMenu(){attachMenu.hidden=true;attachButton.setAttribute('aria-expanded','false')}
attachButton.onclick=function(){attachMenu.hidden=!attachMenu.hidden;attachButton.setAttribute('aria-expanded',String(!attachMenu.hidden))};
document.getElementById('pickDocuments').onclick=function(){closeAttachmentMenu();fileInput.click()};
document.getElementById("composeFile").onclick=function(){closeAttachmentMenu();chooseFileMode(null)};
document.getElementById("newWorkspaceFile").onclick=function(){chooseFileMode(null)};
document.getElementById('pickImages').onclick=function(){closeAttachmentMenu();imageInput.click()};
document.getElementById('takePhoto').onclick=function(){closeAttachmentMenu();cameraInput.click()};
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeAttachmentMenu()});
document.addEventListener('click',function(e){if(!attachMenu.hidden&&!attachMenu.contains(e.target)&&!attachButton.contains(e.target))closeAttachmentMenu()});
var selectedFiles=[];
var selectedFileData=new WeakMap();
function cacheSelectedFile(f){
  if(!selectedFileData.has(f)){
    var result=fileBase64(f).then(function(data){return {ok:true,data:data}},function(err){console.warn('IAchat file read failed',f.name,err&&err.name);return {ok:false}});
    selectedFileData.set(f,result);
  }
  return selectedFileData.get(f);
}
function selectedAttachments(){return selectedFiles.slice()}
function showSelectedAttachments(){
  var host=document.getElementById('selectedFiles');host.replaceChildren();
  selectedFiles.forEach(function(f,index){
    var chip=document.createElement('span');chip.className='selected-file';
    var name=document.createElement('span');name.textContent=f.name;
    var remove=document.createElement('button');remove.type='button';remove.textContent='×';
    remove.setAttribute('aria-label','Quitar '+f.name);
    remove.onclick=function(){selectedFiles.splice(index,1);showSelectedAttachments()};
    chip.append(name,remove);host.appendChild(chip);
  });
}
function addSelectedFiles(e){
  var incoming=Array.from(e.target.files||[]);
  var available=Math.max(0,5-selectedFiles.length);
  if(incoming.length>available){alert('Podés adjuntar como máximo 5 archivos por mensaje.');}
  incoming.slice(0,available).forEach(function(f){
    if(f.size>2000000){alert('El archivo "'+f.name+'" supera los 2 MB permitidos.');return}
    if(selectedFiles.some(function(existing){return existing.name===f.name&&existing.size===f.size&&existing.lastModified===f.lastModified})){return}
    selectedFiles.push(f);cacheSelectedFile(f);
  });
  e.target.value='';showSelectedAttachments();
}
fileInput.onchange=addSelectedFiles;
imageInput.onchange=addSelectedFiles;
cameraInput.onchange=async function(e){
  var photo=(e.target.files||[])[0];
  e.target.value='';
  if(!photo)return;
  if(selectedFiles.length>=5){alert('Podés adjuntar como máximo 5 archivos por mensaje.');return}
  try{
    var image=await createImageBitmap(photo);
    var scale=Math.min(1,1600/Math.max(image.width,image.height));
    var canvas=document.createElement('canvas');
    canvas.width=Math.max(1,Math.round(image.width*scale));
    canvas.height=Math.max(1,Math.round(image.height*scale));
    var ctx=canvas.getContext('2d');
    if(!ctx)throw Error('canvas_unavailable');
    ctx.drawImage(image,0,0,canvas.width,canvas.height);
    if(image.close)image.close();
    var blob=null;
    for(var quality of [0.85,0.7,0.55,0.4]){
      blob=await new Promise(function(resolve){canvas.toBlob(resolve,'image/jpeg',quality)});
      if(blob&&blob.size<=2000000)break;
    }
    if(!blob||blob.size>2000000)throw Error('image_too_large');
    var filename='foto-'+new Date().toISOString().replace(/[:.]/g,'-')+'.jpg';
    var converted=new File([blob],filename,{type:'image/jpeg',lastModified:Date.now()});
    addSelectedFiles({target:{files:[converted],value:''}});
  }catch(err){
    console.warn('IAchat camera processing failed',err&&err.message);
    alert('No se pudo preparar la foto. Probá adjuntarla desde Imágenes.');
  }
};
function fileBase64(f){return new Promise(function(resolve,reject){var rd=new FileReader();rd.onload=function(){var data=String(rd.result||'').split(',')[1];if(data)resolve(data);else reject(new Error('empty_file_data'))};rd.onerror=function(){reject(rd.error||new Error('file_read_error'))};rd.onabort=function(){reject(new Error('file_read_aborted'))};try{rd.readAsDataURL(f)}catch(err){reject(err)}})}


async function syncWorkspaceFiles(){
 var box=document.getElementById('workspaceFiles');box.replaceChildren();
 var r=await fetch('/api/files',{cache:'no-store'});if(!r.ok)return;
 var data=await r.json();
 if(!data.files.length){box.textContent='Todavía no hay archivos.';return}
 data.files.forEach(function(file){
  var wrap=document.createElement('div');wrap.style.cssText='display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin:6px 0';
  var link=document.createElement('a');link.href='/api/files/'+encodeURIComponent(file.id)+'/download';link.textContent='↓ '+file.name;link.setAttribute('download',file.name);link.style.cssText='color:var(--accent);flex:1;overflow-wrap:anywhere';
  var edit=document.createElement('button');edit.textContent='Editar';edit.onclick=function(){chooseFileMode(file.id)};
  var del=document.createElement('button');del.textContent='×';del.setAttribute('aria-label','Borrar '+file.name);del.onclick=async function(){
   if(!confirm('¿Eliminar '+file.name+'?'))return;
   var q=await fetch('/api/files/'+encodeURIComponent(file.id),{method:'DELETE'});if(q.ok)syncWorkspaceFiles()
  };
  wrap.append(link,edit,del);box.append(wrap);
 })
}
async function submitFileMode(text){
 var payload={instruction:text};if(editFileId)payload.file_id=editFileId;
 var waiting=add('assistant','Generando archivo…');
 try{
  var r=await fetch('/api/files/generate',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)});
  var d=await r.json();waiting.remove();
  if(!r.ok){alert('No se generó el archivo: '+(d.detail||'error HTTP '+r.status));if(r.status===401)showLogin();return}
  add('user',text);var node=add('assistant','Archivo listo: ');
  var link=document.createElement('a');link.href='/api/files/'+encodeURIComponent(d.id)+'/download';link.textContent='↓ '+d.name;link.setAttribute('download',d.name);link.style.color='var(--accent)';node.append(link);
  input.value='';clearFileMode();syncWorkspaceFiles().catch(function(){});
 }catch(err){if(waiting.isConnected)waiting.remove();alert('No se pudo generar el archivo. Podés reintentar.')}
}

document.getElementById('form').onsubmit=async function(e){e.preventDefault();if(busy)return;var text=input.value.trim(),files=selectedAttachments();if(fileMode){if(!text)return;if(files.length){alert('Quitá los adjuntos antes de generar un archivo.');return}busy=true;try{await submitFileMode(text)}finally{busy=false}return}if(!text&&!files.length)return;if(files.length>5){alert('Podés adjuntar como máximo 5 archivos.');return}
var oversized=files.find(f=>f.size>2000000);
if(oversized){alert('El archivo "'+oversized.name+'" pesa '+(oversized.size/1000000).toFixed(2)+' MB. El máximo es 2 MB por archivo.');return}
var invalid=files.find(f=>!['.txt','.md','.pdf','.jpg','.jpeg','.png','.webp'].some(ext=>f.name.toLowerCase().endsWith(ext)));
if(invalid){alert('El archivo "'+invalid.name+'" no es PDF, TXT, MD, JPG, PNG ni WebP.');return}
var requestStartedAt=performance.now();busy=true;var waiting=add('assistant','Enviando…');var payload={text:text,project:activeProject()};if(conversationId)payload.conversation_id=conversationId;
var stage='reading_files';var accepted=false;try{payload.attachments=await Promise.all(files.map(async function(f){
  var cached=await cacheSelectedFile(f);
  if(!cached.ok)throw new Error('file_read_failed_reselect');
  return {name:f.name,content_base64:cached.data};
}));stage='sending_request';var r=await fetch('/api/chat',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)});var raw=await r.text(),d;try{d=JSON.parse(raw)}catch(_){d={detail:'El servidor respondió con un error no válido.'}}waiting.remove();if(!r.ok){var detail=typeof d.detail==='string'?d.detail:'No se pudo procesar el adjunto';alert('No se envió el mensaje (HTTP '+r.status+'): '+detail+'. Podés reintentar.');if(r.status===401)showLogin();return}if(!d||typeof d.answer!=='string'||!d.conversation_id){alert('El servidor devolvió una respuesta incompleta. Conservamos tu mensaje para reintentar.');return}accepted=true;var sent=add('user',text);payload.attachments.forEach(function(a,i){var f=files[i],ext=f.name.toLowerCase();if(/\.(jpg|jpeg|png|webp)$/.test(ext)){var img=document.createElement('img');img.className='sent-image';img.alt='Imagen adjunta: '+f.name;img.src='data:'+(ext.endsWith('.png')?'image/png':ext.endsWith('.webp')?'image/webp':'image/jpeg')+';base64,'+a.content_base64;sent.appendChild(img)}else{var note=document.createElement('div');note.className='sent-file';note.textContent='📄 '+f.name;sent.appendChild(note)}});input.value='';selectedFiles=[];fileInput.value='';imageInput.value='';showSelectedAttachments();conversationId=d.conversation_id;ids=ids.filter(function(x){return x.id!==conversationId});ids.unshift({id:conversationId,title:text.slice(0,55),project:activeProject()});saveIds();syncHistory().catch(function(){});var responseNode=add('assistant',d.answer);
if(Array.isArray(d.web_sources)&&d.web_sources.length){
 var sourcesBox=document.createElement('div');sourcesBox.className='web-sources';
 sourcesBox.style.cssText='margin-top:10px;padding-top:8px;border-top:1px solid var(--edge);font-size:12px;overflow-wrap:anywhere';
 var heading=document.createElement('div');heading.textContent='Enlaces encontrados (no verificados independientemente):';heading.style.cssText='color:var(--muted);margin-bottom:5px';sourcesBox.append(heading);
 d.web_sources.slice(0,3).forEach(function(source,i){
  if(!source||typeof source.url!=='string')return;
  try{var parsed=new URL(source.url);if(parsed.protocol!=='https:')return}
  catch(_){return}
  var a=document.createElement('a');a.href=source.url;a.target='_blank';a.rel='noopener noreferrer';
  a.textContent=(i+1)+'. '+(source.title||parsed.hostname);a.style.cssText='display:block;margin:3px 0';
  sourcesBox.append(a);
 });
 responseNode.append(sourcesBox);
}
addResponseTiming(responseNode,performance.now()-requestStartedAt,new Date())}
catch(err){if(waiting.isConnected)waiting.remove();if(accepted){console.error('IAchat display failure after successful send',err);alert('El mensaje se envió, pero hubo un problema al actualizar la pantalla. Recargá la conversación antes de reintentar para evitar duplicados.');return}var reason=err&&err.name==='TypeError'?'No se pudo completar la solicitud HTTP. Puede ser un problema de conexión, proxy o límite de carga.':err&&err.name==='AbortError'?'La solicitud fue interrumpida.':'Error inesperado al preparar o enviar el mensaje.';console.error('IAchat upload failure',stage,err);alert((stage==='reading_files'?'No se pudo leer el archivo. Quitá el adjunto y volvé a seleccionarlo desde Imágenes o Documentos. ':reason)+' El texto sigue disponible para reintentar.')}finally{busy=false}};
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
SERVICE_WORKER = """const CACHE='iachat-shell-v15';
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
