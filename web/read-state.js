/* Transactions serialize per-piece writes. Legacy snapshots are never authoritative after import. */
(function(root){
 'use strict';
 const readSet=new Set(),listeners=new Set(),sessionChanges=new Map();
 let db=null,persistent=true,channel=null;
 const noticeKey='alicanto_read_v3_notice';
 function legacy(key){try{const x=JSON.parse(localStorage.getItem(key));return Array.isArray(x)?x:[]}catch{return[]}}
 function notify(){for(const fn of listeners)fn({persistent});}
 function unavailable(){persistent=false;notify();}
 function transaction(mode,work){return new Promise((resolve,reject)=>{const tx=db.transaction(['pieces','meta'],mode);let result;try{result=work(tx.objectStore('pieces'),tx.objectStore('meta'))}catch(e){tx.abort();reject(e);return}tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||Error('Read transaction aborted'));});}
 async function refresh(){if(!db)return;const rows=[];await transaction('readonly',pieces=>{const req=pieces.openCursor();req.onsuccess=()=>{const cur=req.result;if(cur){rows.push(cur.value);cur.continue()}}});readSet.clear();for(const x of rows)if(x.read)readSet.add(x.piece_id);for(const [id,value] of sessionChanges){if(value)readSet.add(id);else readSet.delete(id)}notify();}
 async function migrate(marker,entries,options={}){
  await ready;if(!db)return;
  await transaction('readwrite',(pieces,meta)=>{const gate=meta.get(marker);gate.onsuccess=()=>{
   if(gate.result)return;
   for(const [id,aliases,provenance] of entries){const existing=pieces.get(id);existing.onsuccess=()=>{
    if(existing.result||!aliases.length)return;
    let pending=aliases.length;const records=[];
    for(const alias of aliases){const req=pieces.get(alias);req.onsuccess=()=>{
     if(req.result)records.push(req.result);
     if(--pending)return;
     // Explicit v3 updates, including false tombstones, supersede stale legacy reads.
     const explicit=records.filter(x=>x.sequence||x.updated_at).sort((a,b)=>(b.sequence||0)-(a.sequence||0)||String(b.updated_at||'').localeCompare(String(a.updated_at||''))||Number(a.read)-Number(b.read));
     if(explicit.length){const latest=explicit[0];if(!options.legacyOnly||latest.read===false)pieces.put({piece_id:id,read:latest.read,sequence:latest.sequence,updated_at:latest.updated_at,provenance:'alias_v3'});return}
     const found=records.some(x=>x.read===true&&(!options.legacyOnly||String(x.provenance||'').startsWith('legacy')));
     if(found)pieces.put({piece_id:id,read:true,provenance});
    }}
   }}
   meta.put({id:marker,complete:true});
  }});
  await refresh();broadcast();
 }
 function broadcast(){channel?.postMessage({changed:true});try{localStorage.setItem(noticeKey,String(Date.now())+Math.random())}catch{}}
 const ready=new Promise(resolve=>{try{
  const request=indexedDB.open('alicanto_read_v3',1);
  request.onupgradeneeded=()=>{request.result.createObjectStore('pieces',{keyPath:'piece_id'});request.result.createObjectStore('meta',{keyPath:'id'})};
  request.onerror=()=>{unavailable();resolve()};request.onblocked=()=>{unavailable();resolve()};
  request.onsuccess=async()=>{db=request.result;db.onversionchange=()=>{db.close();db=null;unavailable()};try{
   const ids=[...new Set([...legacy('alicanto_read'),...legacy('radar_read'),...legacy('alicanto_global_read').map(id=>'global:'+id)])];
   await transaction('readwrite',(pieces,meta)=>{const gate=meta.get('legacy-v1');gate.onsuccess=()=>{if(gate.result)return;for(const id of ids){const req=pieces.get(id);req.onsuccess=()=>{if(!req.result)pieces.put({piece_id:id,read:true,provenance:'legacy_read'})}}meta.put({id:'legacy-v1',complete:true})}});
   await refresh();
  }catch{unavailable()}resolve()};
 }catch{unavailable();resolve()}});
 async function set(id,read){
  await ready;
  if(!db){sessionChanges.set(id,!!read);if(read)readSet.add(id);else readSet.delete(id);notify();return false}
  try{
   await transaction('readwrite',(pieces,meta)=>{const seq=meta.get('sequence');seq.onsuccess=()=>{const sequence=(seq.result?.value||0)+1;pieces.put({piece_id:id,read:!!read,sequence,updated_at:new Date().toISOString()});meta.put({id:'sequence',value:sequence})}});
   sessionChanges.delete(id);persistent=sessionChanges.size===0;await refresh();broadcast();return true;
  }catch{sessionChanges.set(id,!!read);if(read)readSet.add(id);else readSet.delete(id);unavailable();return false}
 }
 // One transaction for bulk actions (mark all, undo all) instead of one write and refresh per piece.
 async function setMany(ids,read){
  await ready;ids=[...new Set(ids)];if(!ids.length)return true;
  if(!db){for(const id of ids){sessionChanges.set(id,!!read);if(read)readSet.add(id);else readSet.delete(id)}notify();return false}
  try{
   await transaction('readwrite',(pieces,meta)=>{const seq=meta.get('sequence');seq.onsuccess=()=>{let sequence=seq.result?.value||0;const at=new Date().toISOString();for(const id of ids)pieces.put({piece_id:id,read:!!read,sequence:++sequence,updated_at:at});meta.put({id:'sequence',value:sequence})}});
   for(const id of ids)sessionChanges.delete(id);persistent=sessionChanges.size===0;await refresh();broadcast();return true;
  }catch{for(const id of ids){sessionChanges.set(id,!!read);if(read)readSet.add(id);else readSet.delete(id)}unavailable();return false}
 }
 if(typeof BroadcastChannel!=='undefined'){channel=new BroadcastChannel('alicanto_read_v3');channel.onmessage=()=>ready.then(refresh).catch(unavailable)}
 root.addEventListener?.('storage',e=>{if(e.key===noticeKey)ready.then(refresh).catch(unavailable)});
 root.addEventListener?.('pageshow',()=>ready.then(refresh).catch(unavailable));
 root.document?.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')ready.then(refresh).catch(unavailable)});
 root.AlicantoRead={readSet,ready,set,setMany,migrate,refresh,subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn)},get persistent(){return persistent}};
})(typeof window==='undefined'?globalThis:window);
