/* Anonymous event schema. Until a provider and privacy treatment are approved,
   this file makes no analytics requests, assigns no identifiers and stores nothing.
   Providers (data/analytics.json, both flags must be true): 'posthog' (per-event random ID) or 'goatcounter'
   (proposal 10-nov-2026: cookieless, no identifiers; endpoint https://<code>.goatcounter.com/count only; the page
   path is sent without query string or hash, and events carry only their fixed name). */
(async()=>{
  let returning=false;
  try{returning=Boolean(localStorage.getItem('alicanto_last_visit'))}catch{}
  let cfg;
  try{
    const response=await fetch('data/analytics.json',{cache:'no-store'});
    if(!response.ok)return;
    cfg=await response.json();
  }catch{return}
  if(cfg.enabled!==true||cfg.privacy_approved!==true)return;
  const allowedHosts=new Set(['https://us.i.posthog.com','https://eu.i.posthog.com']);
  const GOAT_ENDPOINT=/^https:\/\/[a-z0-9-]{2,50}\.goatcounter\.com\/count$/;
  let send;
  if(cfg.provider==='goatcounter'&&typeof cfg.goatcounter_endpoint==='string'&&GOAT_ENDPOINT.test(cfg.goatcounter_endpoint)){
    // Path only (no ?query, no #hash): ficha ids, filters and share links never leave the browser.
    window.goatcounter={path:()=>location.pathname,allow_local:false};
    const script=document.createElement('script');
    script.async=true;script.src='https://gc.zgo.at/count.js';
    script.dataset.goatcounter=cfg.goatcounter_endpoint;
    document.head.appendChild(script);
    send=event=>{
      if(event==='visit')return;  // the page view is counted by count.js itself
      const fire=()=>window.goatcounter&&typeof window.goatcounter.count==='function'&&
        window.goatcounter.count({path:`evento/${event}`,title:event,event:true});
      if(window.goatcounter&&typeof window.goatcounter.count==='function')fire();else script.addEventListener('load',fire,{once:true});
    };
  }else if(cfg.provider==='posthog'&&typeof cfg.project_key==='string'&&cfg.project_key&&allowedHosts.has(cfg.host)){
  send=(event,properties={})=>{
    // Fresh per-event ID: no user ID, session ID, URL, title, email or free text.
    const distinct_id=crypto.randomUUID();
    const body={api_key:cfg.project_key,event,distinct_id,
      properties:{...properties,$geoip_disable:true,$process_person_profile:false}};
    fetch(`${cfg.host}/capture/`,{method:'POST',mode:'cors',keepalive:true,
      headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).catch(()=>{});
  };
  }else return;
  send('visit',{returning});
  document.addEventListener('click',event=>{
    const target=event.target.closest('button,a,summary');
    if(!target)return;
    if(target.matches('[data-brief]'))send('brief_open');
    else if(target.matches('[data-brief-read]'))send('brief_mark_read');
    else if(target.matches('[data-detail]'))send('card_open');
    else if(target.matches('[data-read]'))send('card_read_toggle');
    else if(target.matches('#typeFilters .chip,#scopeFilters .chip'))send('facet_change');
    else if(target.matches('.signal a[target="_blank"],#signalDetail a[target="_blank"]'))send('source_click');
    else if(target.matches('#filterDetails summary'))send('filters_open');
    else if(target.matches('[data-open-premium]'))send('premium_cta');
    else if(target.matches('[data-open-newsletter]'))send('newsletter_open');
    else if(target.matches('a.dx-row'))send('datos_ficha_open');
  },true);
  document.addEventListener('change',event=>{
    const input=event.target;
    if(input.matches('#period'))send('period_change');
    else if(input.matches('#sort'))send('sort_change');
    else if(input.matches('#seriesLargas [data-sl="serie"]'))send('datos_serie_change');
  },true);
  document.addEventListener('submit',event=>{
    if(event.target.matches('#subscriptionForm'))send('email_signup_intent');
  },true);
})();
