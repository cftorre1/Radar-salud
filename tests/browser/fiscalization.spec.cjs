const {test,expect,selectPeriod}=require('./fixtures.cjs');
const fs=require('node:fs');

test('fiscalization reconciliation preserves act dates and separates reviewed normativa',async({page})=>{
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.goto('/');
 await expect(page.locator('#meta')).toContainText('Última actualización:');
 await page.locator('#filterDetails summary').click();
 await selectPeriod(page,'90');
 const radar=await (await page.request.get('/data/radar_today.json')).json();
 const pulse=radar.signals.find(signal=>signal.title.startsWith('Pulso de sanciones a Prestadores'));
 expect(pulse).toBeTruthy();
 expect(pulse.publication_date).toBe('2026-09-15');
 expect(pulse.event_date_basis).toBe('publication');
 expect(pulse.source_alternatives).toHaveLength(3);
 expect(pulse.source_alternatives.map(source=>source.event_date).sort()).toEqual(['2026-09-03','2026-09-08','2026-09-08']);
 const pulseCard=page.locator('article[data-card]').filter({has:page.getByRole('heading',{name:pulse.title,exact:true})});
 await pulseCard.locator('[data-detail]').first().click();await expect(page.locator('#detailBody')).toContainText('Clínica Los Carrera');
 await expect(page.locator('#detailBody .sourceverify .related-item')).toHaveCount(3);
 await expect(page.locator('#detailBody')).toContainText('200 UF');
 // The act date used to be read from the card_why paragraph; news fichas no longer carry it (Dirección 28-oct
 // 08:20, punto 4), so the pulse's own publication date is checked on the ficha's dated origin line.
 await expect(page.locator('#detailBody .ficha-sources > p.source')).toContainText('Publicado 15 sept 2026');
 await page.getByRole('button',{name:'Cerrar ficha'}).click();
 const instruction=radar.signals.find(signal=>signal.source_url?.endsWith('w3-article-791293.html'));
 expect(instruction.signal_types).toEqual(['Normativa']);
 expect(instruction.scopes).toEqual(expect.arrayContaining(['Isapres','COMPIN']));
 expect(instruction.ingestion_mode).toBe('BACKFILL');
 const instructionCard=page.locator('article[data-card]').filter({has:page.getByRole('heading',{name:instruction.display_title,exact:true})});
 await expect(instructionCard).toBeVisible();
 await instructionCard.locator('[data-detail]').first().click();
 await expect(page.locator('#detailBody')).toContainText('30 de septiembre');
 await expect(page.locator('#detailBody a[href="https://www.suseso.gob.cl/612/w3-article-791293.html"]').first()).toBeVisible();
 await page.getByRole('button',{name:'Cerrar ficha'}).click();
 const recovered=radar.signals.find(signal=>signal.source_url?.includes('ip-n-7462'));
 expect(recovered.event_date).toBe('2026-09-23');
 expect(recovered.publication_date).toBeNull();
 expect(recovered.sanction_amount).toBe(400);
 expect(recovered.ingestion_mode).toBe('BACKFILL');
 const amendment=radar.signals.find(signal=>signal.source_url?.includes('if-n9774'));
 expect(amendment.event_type).toBe('SANCTION_AMENDMENT');
 expect(amendment.event_date).toBe('2026-08-20');
 expect(amendment.validity_text).toContain('Ejecución suspendida');
 expect(errors).toEqual([]);
});

test('recovered registers retain offices, actors, effects and issuance dates in grouped details',async({page},testInfo)=>{
 const errors=[];page.on('pageerror',error=>errors.push(error.message));await page.goto('/');
 await expect(page.locator('#meta')).toContainText('Última actualización:');
 await page.locator('#filterDetails summary').click();await selectPeriod(page,'90');
 const radar=await (await page.request.get('/data/radar_today.json')).json();
 const register=radar.signals.find(s=>s.source_record_id==='suseso_emisores:rolling90');
 // The original native control stays fixed; its rolling window ages with the
 // snapshot date. Expected identities come from that control, not the UI data.
 const ledger=JSON.parse(fs.readFileSync('data/audits/fiscalizacion/native_stock_ledger_2026_10_11.json','utf8'));
 const history=JSON.parse(fs.readFileSync('data/history/superintendencia_signals.json','utf8')).signals;
 const original=ledger.filter(s=>s.source==='suseso_fiscalizacion'&&s.document_class==='enforcement_sanction'&&s.decision==='published');
 expect(original).toHaveLength(92);
 expect(radar.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
 const anchor=Date.parse(radar.date+'T00:00:00Z');
 expect(new Date(anchor).toISOString().slice(0,10)).toBe(radar.date);
 const start30=new Date(anchor-30*86400000).toISOString().slice(0,10);
 const start90=new Date(anchor-90*86400000).toISOString().slice(0,10);
 const recent=original.filter(s=>s.emission_date>=start90&&s.emission_date<=radar.date);
 const issued30=recent.filter(s=>s.emission_date>=start30);
 const metadata=new Map(history.map(s=>[s.source_record_id,s]));
 const context=original.filter(s=>{const m=metadata.get(s.source_record_id);return s.emission_date<start90&&m?.suspension_start<=radar.date&&m?.suspension_end>=radar.date});
 expect(recent.length).toBeGreaterThan(0);
 // The fixed 2026-10-11 control must be fully present. Later captures may add
 // sanctions detected after that control (e.g. the 12–24 oct backlog); those
 // extras must be durable history rows detected after the control, in window.
 const shown=register.source_alternatives.map(s=>s.source_record_id);
 const controlIds=new Set(recent.map(s=>s.source_record_id));
 expect(recent.map(s=>s.source_record_id).filter(id=>!shown.includes(id))).toEqual([]);
 const extras=shown.filter(id=>!controlIds.has(id));
 for(const id of extras){const m=metadata.get(id);expect(m,id).toBeTruthy();expect(String(m.detected_at)>'2026-10-12',id).toBe(true);expect(m.emission_date>=start90&&m.emission_date<=radar.date,id).toBe(true)}
 const extras30=extras.filter(id=>metadata.get(id).emission_date>=start30).length;
 expect(register.counts).toEqual({'30':issued30.length+extras30,'90':recent.length+extras.length});expect(register.publication_date).toBeNull();
 const card=page.locator('article[data-card]').filter({has:page.getByRole('heading',{name:register.title,exact:true})});
 await expect(card).toBeVisible();await expect(card.locator('.card-meta')).toContainText('Emitido');
 await expect(card.locator('.card-meta')).toContainText('Publicación no verificada');
 await card.locator('[data-detail]').first().click();
 await expect(page.locator('#detailBody .sourceverify:not(.historical-sanctions) .related-item')).toHaveCount(recent.length+extras.length);
 expect(register.historical_sanction_context.map(s=>s.source_record_id).sort()).toEqual(context.map(s=>s.source_record_id).sort());
 expect(register.historical_sanction_context.every(s=>s.emission_date<start90&&s.publication_date===null)).toBe(true);
 const originalDates=new Map(original.map(s=>[s.source_record_id,s.emission_date]));
 // Extras detected after the control take their issuance date from durable history.
 for(const id of extras)originalDates.set(id,metadata.get(id).emission_date);
 expect([...register.source_alternatives,...register.historical_sanction_context].every(s=>s.emission_date===originalDates.get(s.source_record_id)&&s.event_date===s.emission_date&&s.publication_date===null)).toBe(true);
 await expect(page.locator('#detailBody .historical-sanctions .related-item')).toHaveCount(context.length);
 await expect(page.locator('#detailBody .historical-sanctions summary')).toContainText('Suspensiones de oficios históricos');
 await expect(page.locator('#detailBody')).toContainText('anteriores mantienen suspensiones vigentes');
 await page.locator('#detailBody .sourceverify:not(.historical-sanctions) summary').click();
 await expect(page.locator('#detailBody')).toContainText('O-02-S-03209-2026');
 await expect(page.locator('#detailBody')).toContainText('2027-01-04');
 expect(await page.locator('#detailBody').evaluate(e=>e.scrollWidth<=e.clientWidth+2)).toBe(true);
 await page.screenshot({path:testInfo.outputPath('native-register.png')});
 await page.getByRole('button',{name:'Cerrar ficha'}).click();
 const agents=radar.signals.find(s=>s.source_record_id==='sis_agentes:rolling90');
 const originalAgents=ledger.filter(s=>s.source==='superintendencia_fiscalizacion'&&s.actor_category==='Agentes de ventas'&&s.decision==='published');
 expect(originalAgents).toHaveLength(18);
 const recentAgents=originalAgents.filter(s=>s.emission_date>=start90&&s.emission_date<=radar.date);
 const recentAgents30=recentAgents.filter(s=>s.emission_date>=start30);
 expect(agents.counts).toEqual({'30':recentAgents30.length,'90':recentAgents.length});
 expect(agents.source_alternatives.map(s=>s.url).sort()).toEqual(recentAgents.map(s=>s.url).sort());
 expect(agents.publication_date).toBeNull();
 const originalAgentDates=new Map(originalAgents.map(s=>[s.url,s]));
 expect(agents.source_alternatives.every(s=>s.emission_date===originalAgentDates.get(s.url)?.emission_date&&s.event_date===s.emission_date&&s.publication_date===originalAgentDates.get(s.url)?.publication_date)).toBe(true);
 expect(agents.source_alternatives.some(s=>s.material.includes('Doris del Pilar Alcántara Poblete'))).toBe(true);
 const agentMetadata=new Map(history.map(s=>[s.source_url,s]));
 const substitutions=recentAgents.filter(s=>agentMetadata.get(s.url)?.event_type==='SANCTION_SUBSTITUTION').length;
 expect(agents.what_happened).toMatch(new RegExp(`(?<![\\d.,])${substitutions} multas impagas sustituidas\\b`));
 const agentCard=page.locator('article[data-card]').filter({has:page.getByRole('heading',{name:agents.title,exact:true})});
 await agentCard.locator('[data-detail]').first().click();await expect(page.locator('#detailBody .sourceverify .related-item')).toHaveCount(recentAgents.length);
 await page.getByRole('button',{name:'Cerrar ficha'}).click();
 const report=radar.signals.find(s=>s.event_type==='FISCALIZATION_REPORT'&&s.source_url.includes('superdesalud'));
 expect(report.what_happened).toContain('93.070');expect(report.fact_period).toContain('30 de abril de 2026');
 expect(errors).toEqual([]);
});
