const fs=require('fs'),path=require('path'),{execFileSync}=require('child_process');
const {chromium}=require('/workspace/work/radar-contract/node_modules/playwright');
const root='/workspace/work/radar-contract',out='/workspace/work/reviewer-contract';
const baseline=process.env.REVIEW_SHA||'74da1c6d33b9e5746e79e0f481be3057f33d45df';
const suffix=process.env.REVIEW_SUFFIX||'baseline';
const appSource=baseline==='working-tree'?fs.readFileSync(root+'/web/app.js','utf8'):execFileSync('git',['show',baseline+':web/app.js'],{cwd:root,encoding:'utf8'});
const input=JSON.parse(fs.readFileSync(out+'/signed-surface-probe.json','utf8'))[0];
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const results=[];
 for(const width of [1440,390]){
  const context=await browser.newContext({viewport:{width,height:width===1440?900:844}}),page=await context.newPage();
  await page.clock.install({time:new Date('2026-10-12T15:00:00Z')});
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url());let file=url.pathname==='/'?'index.html':decodeURIComponent(url.pathname.slice(1));
   if(file==='data/radar_today.json')return route.fulfill({json:{generated_at:'2026-10-12T15:00:00Z',signals:input.exported}});
   if(file==='data/free_value.json')return route.fulfill({json:{}});
   if(file==='app.js')return route.fulfill({contentType:'text/javascript',body:appSource});
   const filename=path.resolve(root,'web',file);
   if(filename.startsWith(root+'/web/')&&fs.existsSync(filename))return route.fulfill({path:filename});
   return route.fulfill({status:404,body:''});
  });
  await page.goto('http://reviewer.local/');await page.locator('#period').selectOption('90');
  const card=page.locator('[data-card]');await card.waitFor();
  const cardTitle=await card.locator('.title-open').textContent(),inboxTitle=await page.locator('#brief .briefitem strong').textContent();
  const inboxReadAria=await page.locator('#brief [data-brief-read]').getAttribute('aria-label'),shareTitle=await card.locator('[data-share]').getAttribute('data-share-title');
  await card.locator('.title-open').click();
  const detailTitle=await page.locator('#detailTitle').textContent(),opened=await page.locator('#signalDetail').evaluate(el=>el.open);
  const firstBody=await page.locator('#detailBody').textContent();
  await page.screenshot({path:out+`/signed-title-${suffix}-${width}.png`});
  await page.keyboard.press('Escape');await card.getByRole('button',{name:'Más info',exact:true}).click();
  const sameDetail=firstBody===await page.locator('#detailBody').textContent();
  const unreviewedVisible=(await page.locator('main').textContent()).includes(input.after.card_what)||firstBody.includes(input.after.card_what);
  results.push({baseline_sha:baseline,width,expected_signed_title:input.before.title,unreviewed_card_what:input.after.card_what,card_title:cardTitle,inbox_title:inboxTitle,detail_title:detailTitle,inbox_read_aria:inboxReadAria,share_title:shareTitle,opened,same_title_and_more_info_detail:sameDetail,unreviewed_visible:unreviewedVisible,unchanged_hash:input.content_version_unchanged,depth_pass:input.after_depth.ok,publication_pass:input.publication_ready[0]});
  if(process.env.REVIEW_ASSERT==='1'&&(cardTitle!==input.before.title||inboxTitle!==input.before.title||detailTitle!==input.before.title||!inboxReadAria.includes(input.before.title)||shareTitle!==input.before.title||!opened||!sameDetail||unreviewedVisible))throw Error('Signed-copy independent assertion failed');
  await context.close();
 }
 await browser.close();fs.writeFileSync(out+`/signed-title-browser-${suffix}.json`,JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
