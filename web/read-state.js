/* Per-piece transactions preserve concurrent writes and explicit unread states. */
(function(root){
 'use strict';
 const readSet=new Set(),listeners=new Set();
 let db=null,persistent=true,channel=null;
 const noticeKey='alicanto_read_v3_notice';
 function legacy(key){try{const x=JSON.parse(localStorage.getItem(key));return Array.isArray(x)?x:[]}catch{return[]}}
 function notify(){for(const fn of listeners)fn({persistent});}
 function unavailable(){persistent=false;notify();}
 function transaction(mode,work){return new Promise((resolve,reject)=>{const tx=db.transaction(['pieces','meta'],mode);let result;try{result=work(tx.objectStore('pieces'),tx.objectStore('meta'))}catch(e){tx.abort();reject(e);return}tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||Error('Read transaction aborted'));});}
 async function refresh(){if(!db)return;const rows=[];await transaction('readonly',pieces=>{const req=pieces.openCursor();req.onsuccess=()=>{const cur=req.result;if(cur){rows.push(cur.value);cur.continue()}}});readSet.clear();for(const x of rows)if(x.read)readSet.add(x.piece_id);notify();}
 async function migrate(marker,entries){await ready;if(!db)return;await transaction('readwrite',(pieces,meta)=>{const gate=meta.get(marker);gate.onsuccess=()=>{if(gate.result)return;for(const [id,aliases,provenance] of entries){const existing=pieces.get(id);existing.onsuccess=()=>{if(existing.result)return;let pending=aliases.length,found=false;for(const alias of aliases){const req=pieces.get(alias);req.onsuccess=()=>{found=found||req.result?.read===true;if(--pending===0&&found)pieces.put({piece_id:id,read:true,provenance})}}}}meta.put({id:marker,complete:true})}});await refresh();broadcast();}
 function broadcast(){channel?.postMessage({changed:true});try{localStorage.setItem(noticeKey,String(Date.now())+Math.random())}catch{}}
 const ready=new Promise(resolve=>{try{const request=indexedDB.open('alicanto_read_v3',1);request.onupgradeneeded=()=>{request.result.createObjectStore('pieces',{keyPath:'piece_id'});request.result.createObjectStore('meta',{keyPath:'id'})};request.onerror=()=>{unavailable();resolve()};request.onblocked=()=>{unavailable();resolve()};request.onsuccess=async()=>{db=request.result;db.onversionchange=()=>{db.close();db=null;unavailable()};try{const ids=[...new Set([...legacy('alicanto_read'),...legacy('radar_read'),...legacy('alicanto_global_read').map(id=>'global:'+id)])];await transaction('readwrite',(pieces,meta)=>{const gate=meta.get('legacy-v1');gate.onsuccess=()=>{if(gate.result)return;for(const id of ids){const req=pieces.get(id);req.onsuccess=()=>{if(!req.result)pieces.put({piece_id:id,read:true,provenance:'legacy_read'})}}meta.put({id:'legacy-v1',complete:true})}});await refresh()}catch{unavailable()}resolve()}}catch{unavailable();resolve()}});
 async function set(id,read){await ready;if(!db){if(read)readSet.add(id);else readSet.delete(id);notify();return false}try{await transaction('readwrite',pieces=>pieces.put({piece_id:id,read:!!read,updated_at:new Date().toISOString()}));await refresh();broadcast();return true}catch{unavailable();if(read)readSet.add(id);else readSet.delete(id);notify();return false}}
 if(typeof BroadcastChannel!=='undefined'){channel=new BroadcastChannel('alicanto_read_v3');channel.onmessage=()=>ready.then(refresh).catch(unavailable)}
 root.addEventListener?.('storage',e=>{if(e.key===noticeKey)ready.then(refresh).catch(unavailable)});
 root.addEventListener?.('pageshow',()=>ready.then(refresh).catch(unavailable));
 root.document?.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')ready.then(refresh).catch(unavailable)});
 root.AlicantoRead={readSet,ready,set,migrate,refresh,subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn)},get persistent(){return persistent}};
})(typeof window==='undefined'?globalThis:window);
