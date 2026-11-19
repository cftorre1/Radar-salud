// «Escuchar pendientes», phase 1 (Dirección 19-nov-2026): the pending items read aloud as a short podcast with the
// device voice (speechSynthesis). No AI cost: the host's intro, transitions and outro are fixed, reviewed lines,
// rotated by day; the news text is the card's own verified text, rewritten only mechanically for the ear.
// Known limit: browsers stop the device voice when the screen locks; the page asks to keep the screen on while it
// plays (Wake Lock). Listening with the screen locked needs pre-rendered audio (phase 2).
(function(root){
'use strict';
const WPM=150; // Spanish synthetic voice, words per minute
const MODES={corto:{label:'Corto',max:9,sentences:1},extenso:{label:'Extenso',max:19,sentences:3}};
const INTROS=[
 '{saludo}. Bienvenido a Alicanto al oído, las noticias de salud que dejaste pendientes. Soy la voz sintética de Alicanto: sintética, pero puntual. Hoy te cuento {k} en unos {m} minutos.',
 '{saludo}, esto es Alicanto al oído. Prometo ir al grano: {k}, unos {m} minutos y cero comerciales.',
 '{saludo}. Bienvenido a Alicanto al oído, el resumen de salud que se escucha mientras el café se enfría. Tenemos {k} para los próximos {m} minutos.',
 '{saludo}, te habla Alicanto al oído. Una voz que no se cansa ni pide vacaciones, con {k} para ponerte al día en unos {m} minutos.'
];
const TRANSITIONS={
 isapres:'Ahora, una para quienes siguen de cerca a las isapres.',
 fonasa:'Atención, que esta toca a Fonasa.',
 prestadores:'Se viene una noticia importante para los prestadores.',
 laboral:'Pasamos a salud laboral. Si administras licencias o seguros, esta te interesa.',
 farma:'Para la industria farmacéutica y el ISP, ojo con esta.',
 publica:'Ahora, salud pública.',
 normativa:'Toca normativa. De esas que conviene conocer antes de que entren en vigencia.',
 mercado:'Ahora, mercado e inversiones: movimientos con plata de por medio.',
 politica:'Política y presupuesto. Sin discursos largos, lo prometo.',
 datos:'Vamos con cifras. Las justas, para que no se enreden.',
 innovacion:'Y para mirar afuera: innovación y global.',
 insights:'Ahora, el análisis de la semana.'
};
const FIRST={prestadores:'Partimos con una importante para los prestadores.'};
const IMPORTANT='Ahora se viene una importante.';
const HALF=['Vamos en la mitad. Quedan {r}.','Seguimos. Quedan {r}, así que no te bajes todavía.'];
const OUTROS=['Eso es todo por ahora. Lo que escuchaste quedó marcado como leído. {resto}Hasta la próxima.',
 'Y con eso cerramos. Lo escuchado ya está marcado como leído. {resto}Que te vaya bien.'];
const NOTE='Recuerda: es una voz sintética del teléfono; el detalle y las fuentes están en cada ficha.';

// Text for the ear: acronyms and legal shorthand spelled out, symbols said, no ellipses.
const SPOKEN=[[/\bRes\.\s*exenta\b/gi,'resolución exenta'],[/\bRes\.\s/g,'resolución '],[/\bN\s?[°º]\s?/g,'número '],
 [/\bIF\//g,'I F '],[/\bSIS\b/g,'la Superintendencia de Salud'],[/\bSUSESO\b/gi,'la Suseso'],[/\bFNE\b/g,'la Fiscalía Nacional Económica'],
 [/\bISP\b/g,'el I S P'],[/\bCMF\b/g,'la C M F'],[/\bGES\b/g,'G E S'],[/\bCAEC\b/g,'cae'],[/\bUF\b/g,'U F'],[/\bPAD\b/g,'P A D'],
 [/\bDipres\b/g,'Dipres'],[/(\d)\/(\d{4})\b/g,'$1 de $2'],[/(\d)\s?%/g,'$1 por ciento'],[/\s·\s/g,'. '],[/…/g,''],
 [/\s+—\s+/g,', '],[/(\p{L})–(\p{L})/gu,'$1 a $2'],[/\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre) (\d{4})\b/gi,'$1 de $2'],[/\s{2,}/g,' ']];
function speakable(t){let s=String(t||'');for(const [a,b] of SPOKEN)s=s.replace(a,b);s=s.replace(/\b(el|la) (el|la) /gi,'$2 ');s=s.trim().replace(/([^.!?])$/,'$1.');return s.replace(/(^|[.!?]\s+)(\p{Ll})/gu,(m,p,c)=>p+c.toUpperCase())}
function sentences(t,n){const parts=String(t||'').replace(/\s+/g,' ').trim().split(/(?<=[.!?])\s+(?=[\p{Lu}«"(¿¡])/u).filter(Boolean);return parts.slice(0,n).join(' ').trim()}
function fold(x){return String(x||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,' ').trim()}
function restates(what,title){const w=fold(what).slice(0,400),ts=fold(String(title).replace(/^[^:]{0,40}:\s*/,'')).split(' ').filter(x=>x.length>3);return ts.length>=3&&ts.filter(x=>w.includes(x)).length/ts.length>=0.8}
function words(t){return (String(t).match(/\S+/g)||[]).length}
function plural(n,one,many){return `${n===1?'una':n} ${n===1?one:many}`}
function greeting(h){return h<12?'Buenos días':h<20?'Buenas tardes':'Buenas noches'}

// items: [{id, kind:'noticia'|'datos'|..., title, what, topic, important}] in feed order (pending only).
function buildScript(items,{mode='corto',hour=12,day=0}={}){
 const m=MODES[mode]||MODES.corto,budget=m.max*WPM,blocks=[];let used=0;
 // group by topic, keeping the feed order of first appearance (transitions then mean something)
 const order=[],groups=new Map();for(const it of items){const k=it.topic||'otros';if(!groups.has(k)){groups.set(k,[]);order.push(k)}groups.get(k).push(it)}
 const sorted=order.flatMap(k=>groups.get(k));
 for(const it of sorted){
  const body=it.kind==='datos'
   ?`Nueva ficha de datos: ${speakable(it.title)}${it.period?` Con datos de ${speakable(it.period).replace(/\.$/,'').toLowerCase()}.`:''} Las cifras conviene mirarlas en la ficha, con su gráfico.`
   :(!it.paywalled&&restates(it.what,it.title))?speakable(sentences(it.what,m.sentences))
   :[speakable(it.title),it.paywalled?'Es una nota con muro de pago: el detalle está en la fuente.':speakable(sentences(it.what,m.sentences))].filter(Boolean).join(' ');
  const w=words(body)+12;if(blocks.length&&used+w>budget)break;used+=w;blocks.push({it,body});
 }
 const k=blocks.length,left=items.length-k,mins=Math.max(1,Math.round((used+60)/WPM));
 const segs=[{id:null,text:INTROS[day%INTROS.length].replace('{saludo}',greeting(hour)).replace('{k}',plural(k,'noticia','noticias')).replace('para los próximos {m} minutos',mins===1?'para el próximo minuto':`para los próximos ${mins} minutos`).replace('unos {m} minutos',mins===1?'un minuto':`unos ${mins} minutos`).replace('{m} minutos',mins===1?'un minuto':`${mins} minutos`)}];
 let prev=null;blocks.forEach((b,i)=>{
  const t=b.it.topic||'otros';let lead='';
  if(t!==prev)lead=speakable((i===0&&FIRST[t])||TRANSITIONS[t]||'');
  else if(b.it.important)lead=IMPORTANT;
  if(k>=8&&i===Math.floor(k/2))lead=[HALF[day%HALF.length].replace('{r}',plural(k-i,'noticia','noticias')),lead].filter(Boolean).join(' ');
  prev=t;segs.push({id:b.it.id,text:[lead,b.body].filter(Boolean).join(' ')});
 });
 const resto=left>0?`Te ${left===1?'queda':'quedan'} ${plural(left,'pendiente','pendientes')} en la app; ${mode==='corto'?'el modo extenso cubre más':'quedan para la próxima'}. `:'';
 segs.push({id:null,text:OUTROS[day%OUTROS.length].replace('{resto}',resto)+' '+NOTE});
 return {segments:segs,minutes:mins,included:k,left};
}

// --- player (browser only) ---
function pickVoice(){const vs=(root.speechSynthesis&&speechSynthesis.getVoices())||[];const es=vs.filter(v=>/^es/i.test(v.lang));
 const score=v=>(/es[-_](CL|419|MX|US|AR|CO)/i.test(v.lang)?4:0)+(/premium|enhanced|natural|neural|google|paulina|m[oó]nica|francisca/i.test(v.name)?3:0)+(v.localService?1:0);
 return es.sort((a,b)=>score(b)-score(a))[0]||null}
function Player({onItemDone,onState}){
 let segs=[],i=0,on=false,lock=null;const synth=root.speechSynthesis;
 const wake=async()=>{try{lock=await navigator.wakeLock?.request('screen')}catch(e){lock=null}};
 const unwake=()=>{try{lock&&lock.release()}catch(e){}lock=null};
 const speak=()=>{if(!on)return;if(i>=segs.length){stop();return}const s=segs[i];const u=new SpeechSynthesisUtterance(s.text);const v=pickVoice();if(v){u.voice=v;u.lang=v.lang}else u.lang='es-CL';u.rate=1.02;
  u.onend=()=>{if(!on)return;if(s.id)onItemDone(s.id);i++;speak()};u.onerror=e=>{if(e.error==='interrupted'||e.error==='canceled')return;i++;speak()};onState({playing:true,index:i,seg:s});synth.speak(u)};
 function play(script){segs=script.segments;i=0;on=true;synth.cancel();wake();speak()}
 function pause(){on=false;synth.cancel();unwake();onState({playing:false,index:i,seg:segs[i]})}
 function resume(){if(!segs.length)return;on=true;wake();speak()}           // restarts the current item: iOS pause() is unreliable
 function next(){synth.cancel();i++;if(on)speak();else onState({playing:false,index:i,seg:segs[i]})} // skipping never marks read
 function stop(){on=false;synth.cancel();unwake();segs=[];i=0;onState({playing:false,done:true})}
 document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&on&&!lock)wake()});
 return {play,pause,resume,next,stop,get playing(){return on}};
}

// --- home UI: «Escuchar» button in the bandeja head, mode sheet and a mini player ---
function pendingItems(){
 const ids=[...document.querySelectorAll('#local article[data-card]:not(.read)')].map(a=>a.dataset.card);
 const by=new Map((typeof allSignals!=='undefined'?allSignals:[]).map(s=>[root.idFor(s),s]));// app.js `let` globals are not window properties
 return ids.map(id=>{const s=by.get(id);if(!s)return null;const ts=typeof root.topicsOf==='function'?root.topicsOf(s):[];
  const norma=typeof normaBySignal!=='undefined'&&normaBySignal.has(id);
  return {id,s,kind:s.stats_ficha?'datos':'noticia',title:typeof root.fichaTitle==='function'?root.fichaTitle(s):root.triageTitle(s),
   what:s.card_what||s.what_happened||'',paywalled:s.paywalled===true,period:s.data_period||'',
   topic:s.stats_ficha?'datos':norma?'normativa':((ts[0]||{}).k||'otros'),important:Number(s.radar_score||0)>=85}}).filter(Boolean);
}
function initUI(){
 const mark=document.getElementById('markAllRead'),head=mark&&mark.parentNode;if(!head||!AlicantoListen.supported()||document.getElementById('listenBtn'))return;
 const btn=document.createElement('button');btn.type='button';btn.id='listenBtn';btn.className='listen-btn';
 btn.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 14v-2a9 9 0 0 1 18 0v2"/><rect x="3" y="14" width="4" height="6" rx="1.5"/><rect x="17" y="14" width="4" height="6" rx="1.5"/></svg><span class="listen-lbl">Escuchar</span>';btn.setAttribute('aria-label','Escuchar pendientes');btn.title='Escuchar pendientes';
 head.insertBefore(btn,mark);// filter row, before «marcar todo»: the title row keeps its lanes on one line
 const bar=document.createElement('div');bar.id='listenBar';bar.className='listen-bar';bar.hidden=true;bar.setAttribute('role','region');bar.setAttribute('aria-label','Escuchar pendientes');document.body.appendChild(bar);
 let player=null,script=null;
 const now=()=>new Date();
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const sheet=()=>{const items=pendingItems(),d=now(),opts={hour:d.getHours(),day:Math.floor(d/864e5)};
  const c=buildScript(items,{...opts,mode:'corto'}),e=buildScript(items,{...opts,mode:'extenso'});
  bar.hidden=false;bar.innerHTML=items.length?`<p class="listen-title">Escuchar tus ${items.length} pendientes</p><div class="listen-modes"><button type="button" data-mode="corto">Corto · ${c.minutes} min<small>${c.included} noticias</small></button><button type="button" data-mode="extenso">Extenso · ${e.minutes} min<small>${e.included} noticias</small></button></div><p class="listen-note">Voz sintética del teléfono. Mantén la pantalla encendida: si se bloquea, el audio se detiene. Lo que termines de escuchar queda como leído.</p><button type="button" class="listen-x" data-act="close" aria-label="Cerrar">×</button>`
   :'<p class="listen-title">No tienes pendientes. Nada que escuchar, y eso también es una buena noticia.</p><button type="button" class="listen-x" data-act="close" aria-label="Cerrar">×</button>';
  bar._items=items;bar._opts=opts};
 const render=st=>{if(st.done){bar.hidden=true;bar.innerHTML='';return}
  const seg=st.seg||{},it=(bar._items||[]).find(x=>x.id===seg.id),n=script?script.segments.length:0;
  bar.innerHTML=`<p class="listen-now"><span class="listen-step">${Math.min(st.index+1,n)}/${n}</span> ${esc(it?it.title:(st.index===0?'Introducción':'Cierre'))}</p><div class="listen-ctl"><button type="button" data-act="${st.playing?'pause':'resume'}">${st.playing?'Pausa':'Seguir'}</button><button type="button" data-act="next">Siguiente</button><button type="button" data-act="stop">Terminar</button></div>`};
 btn.addEventListener('click',()=>{if(player&&player.playing)return;sheet()});
 bar.addEventListener('click',ev=>{const b=ev.target.closest('button');if(!b)return;
  if(b.dataset.mode){script=buildScript(bar._items,{...bar._opts,mode:b.dataset.mode});
   player=player||Player({onItemDone:id=>{const it=(bar._items||[]).find(x=>x.id===id);if(it&&typeof root.setReadWithoutReorder==='function')root.setReadWithoutReorder(it.s,true)},onState:render});
   player.play(script);return}
  const a=b.dataset.act;if(a==='close'){bar.hidden=true;bar.innerHTML='';return}if(!player)return;
  if(a==='pause')player.pause();else if(a==='resume')player.resume();else if(a==='next')player.next();else if(a==='stop')player.stop()});
}
root.AlicantoListen={buildScript,speakable,sentences,Player,pickVoice,MODES,supported:()=>!!(root.speechSynthesis&&root.SpeechSynthesisUtterance)};
if(typeof document!=='undefined'){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initUI);else initUI();}
})(typeof window!=='undefined'?window:globalThis);
