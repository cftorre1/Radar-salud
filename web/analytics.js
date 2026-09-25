/* Anonymous event schema. Until a provider and privacy treatment are approved,
   this file makes no analytics requests, assigns no identifiers and stores nothing. */
(async()=>{
  let returning=false;
  try{returning=Boolean(localStorage.getItem('alicanto_last_visit'))}catch{}
  let cfg;
  try{
    const response=await fetch('data/analytics.json',{cache:'no-store'});
    if(!response.ok)return;
    cfg=await response.json();
  }catch{return}
  const allowedHosts=new Set(['https://us.i.posthog.com','https://eu.i.posthog.com']);
  if(cfg.enabled!==true||cfg.privacy_approved!==true||cfg.provider!=='posthog'||
     typeof cfg.project_key!=='string'||!cfg.project_key||!allowedHosts.has(cfg.host))return;
  const send=(event,properties={})=>{
    // Fresh per-event ID: no user ID, session ID, URL, title, email or free text.
    const distinct_id=crypto.randomUUID();
    const body={api_key:cfg.project_key,event,distinct_id,
      properties:{...properties,$geoip_disable:true,$process_person_profile:false}};
    fetch(`${cfg.host}/capture/`,{method:'POST',mode:'cors',keepalive:true,
      headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).catch(()=>{});
  };
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
    else if(target.matches('#filterDetails summary'))send('filter_panel_open');
    else if(target.matches('#newsletterOpen'))send('newsletter_open');
    else if(target.matches('#sourcesOpen'))send('sources_open');
    else if(target.matches('#earlyAccessOpen'))send('early_access_open');
  },true);
  document.addEventListener('change',event=>{
    const input=event.target;
    if(input.matches('#period'))send('period_change');
    else if(input.matches('#sort'))send('sort_change');
  },true);
  document.addEventListener('submit',event=>{
    if(event.target.matches('#subscriptionForm'))send('email_signup_intent');
  },true);
})();
