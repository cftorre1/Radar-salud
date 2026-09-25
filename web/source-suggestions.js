(()=>{
const trigger=document.getElementById('sourceSuggestionOpen');
const dialog=document.getElementById('sourceSuggestionDialog');
const form=document.getElementById('sourceSuggestionForm');
const close=document.getElementById('sourceSuggestionClose');
const feedback=document.getElementById('sourceSuggestionFeedback');
if(!trigger||!dialog||!form||!close||!feedback)return;
const submit=form.querySelector('button[type="submit"]');
submit.disabled=false;

const setFeedback=(message,state='')=>{
  feedback.textContent=message;
  feedback.dataset.state=state;
};
trigger.addEventListener('click',()=>{
  const sources=document.getElementById('sourcesDialog');
  if(sources?.open)sources.close();
  form.elements.started_at.value=new Date().toISOString();
  setFeedback('');
  dialog.showModal();
  form.elements.source_name.focus();
});
close.addEventListener('click',()=>dialog.close());
dialog.addEventListener('click',event=>{
  if(event.target===dialog)dialog.close();
});
form.addEventListener('submit',async event=>{
  event.preventDefault();
  const payload={
    source_name:form.elements.source_name.value,
    source_url:form.elements.source_url.value,
    comment:form.elements.comment.value,
    website:form.elements.website.value,
    started_at:form.elements.started_at.value
  };
  if(!payload.source_name.trim()&&!payload.source_url.trim()){
    setFeedback('Indica el nombre de la fuente o su URL.','error');
    return;
  }
  submit.disabled=true;
  setFeedback('Enviando…');
  try{
    const response=await fetch('/api/source-suggestions',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload)
    });
    const result=await response.json().catch(()=>({}));
    const stored=response.status===201
      && /^src_[0-9a-f]{32}$/.test(result.id||'')
      && result.status==='received';
    if(!stored)throw new Error(result.message||'unavailable');
    form.reset();
    form.elements.started_at.value=new Date().toISOString();
    setFeedback('Gracias. Guardamos tu sugerencia para revisión.','success');
  }catch(error){
    setFeedback('El envío aún no está habilitado. No guardamos tu sugerencia.','error');
  }finally{
    submit.disabled=false;
  }
});
})();
