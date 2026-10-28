// Premium and newsletter dialogs, one source for Chile and Global (Dirección 28-oct, puntos 6 y 7).
// "Suscribirse" and "PREMIUM" open the same dialog in place on both pages: Global never sends the reader to Chile.
// Capture stays fail-closed: the e-mail field is enabled only with an approved, double opt-in HTTPS provider.
// Without JavaScript the header Newsletter link still goes to subscription.html.
(function(){
 'use strict';
 if(typeof document==='undefined')return;
 const PREMIUM=`<dialog id="earlyAccessDialog" class="home-dialog conversion-dialog" aria-labelledby="earlyAccessTitle"><button type="button" class="detail-close" data-close="earlyAccessDialog" aria-label="Cerrar acceso Premium">Cerrar ×</button><span class="conversion-kicker">PREMIUM</span><h2 id="earlyAccessTitle">Ve más allá de la señal.</h2><p class="conversion-lead">Global Intelligence conecta research internacional, contexto estratégico y señales clave para ayudarte a entender qué importa y decidir antes.</p><form id="premiumInterestForm" class="conversion-form"><label for="premiumEmail">Inscríbete al acceso anticipado</label><div class="conversion-row"><input id="premiumEmail" name="email" type="email" autocomplete="email" placeholder="tu@correo.cl" required disabled/><button id="premiumSubmit" type="submit" disabled>Inscribirme</button></div><p id="premiumStatus" class="conversion-status" role="status">Te contactaremos cuando abramos nuevos accesos.</p></form></dialog>`;
 const NEWSLETTER=`<dialog id="newsletterDialog" class="home-dialog conversion-dialog" aria-labelledby="newsletterTitle"><button type="button" class="detail-close" data-close="newsletterDialog" aria-label="Cerrar resumen semanal">Cerrar ×</button><span class="conversion-kicker">RESUMEN SEMANAL</span><h2 id="newsletterTitle">Lo importante de la semana, directo a tu correo.</h2><p class="conversion-lead">Una selección breve de las señales que vale la pena conocer, sin ruido y solo cuando haya algo relevante.</p><div class="subscribe-row"><label class="sr-only" for="homeEmail">Correo electrónico</label><input id="homeEmail" type="email" placeholder="tu@correo.cl" disabled/><button type="button" disabled>Suscribirme</button></div><p class="conversion-foot"><a href="subscription.html">Cómo funciona la suscripción →</a></p></dialog>`;
 const host=document.querySelector('main')||document.body;
 for(const [id,html] of [['earlyAccessDialog',PREMIUM],['newsletterDialog',NEWSLETTER]])if(!document.getElementById(id))host.insertAdjacentHTML('beforeend',html);
 function open(id){const d=document.getElementById(id);if(d&&!d.open)d.showModal()}
 for(const id of ['earlyAccessDialog','newsletterDialog']){const d=document.getElementById(id);d.querySelector('[data-close]').onclick=()=>d.close();d.addEventListener('click',e=>{if(e.target===d)d.close()})}
 document.querySelectorAll('[data-open-premium]').forEach(b=>b.addEventListener('click',e=>{e.preventDefault();open('earlyAccessDialog')}));
 document.querySelectorAll('[data-open-newsletter]').forEach(b=>b.addEventListener('click',e=>{e.preventDefault();open('newsletterDialog')}));
 // #premium opens the dialog on load and on an in-page link, on either page.
 const premiumHash=()=>{if(location.hash==='#premium')requestAnimationFrame(()=>open('earlyAccessDialog'))};premiumHash();window.addEventListener('hashchange',premiumHash);
 const form=document.getElementById('premiumInterestForm'),email=document.getElementById('premiumEmail'),submit=document.getElementById('premiumSubmit'),status=document.getElementById('premiumStatus');
 const closed='Abriremos nuevas invitaciones muy pronto.';
 function approved(value){try{const u=new URL(value);return u.protocol==='https:'?u.href:null}catch{return null}}
 fetch('data/subscription.json',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject()).then(cfg=>{const action=approved(cfg.form_action);if(cfg.capture_enabled===true&&cfg.privacy_approved===true&&cfg.double_opt_in===true&&action){form.action=action;email.disabled=false;submit.disabled=false;status.textContent='Te enviaremos un correo para confirmar tu inscripción.'}else status.textContent=closed}).catch(()=>{status.textContent=closed});
 form.addEventListener('submit',e=>{if(!form.action||email.disabled){e.preventDefault();status.textContent=closed}});
 window.AlicantoConversion={open};
})();
