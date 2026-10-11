// Ordinary public browser navigation for each HTTP-denied sitemap original.
const {chromium}=require('@playwright/test');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const zlib=require('node:zlib');

(async()=>{
 const inventory=JSON.parse(fs.readFileSync('data/audits/provider_inventory_2026_10_11/red_davila.json','utf8'));
 const targets=inventory.items.filter(x=>x.access_error?.status===403);
 const dir='work/provider_davila_browser';fs.mkdirSync(dir,{recursive:true});
 const executable=['/usr/bin/google-chrome','/usr/bin/chromium'].find(x=>fs.existsSync(x));
 if(!executable)throw Error('ordinary native Chrome unavailable');
 const browser=await chromium.launch({executablePath:executable,args:['--no-sandbox']});
 const context=await browser.newContext();
 const results=[];let cursor=0;
 async function worker(){
  const page=await context.newPage();
  while(cursor<targets.length){
   const item=targets[cursor++];const row={url:item.url,method:'ordinary unauthenticated native Chrome; no challenge handling or TLS bypass'};
   try{
    const response=await page.goto(item.url,{waitUntil:'domcontentloaded',timeout:12000});
    row.status=response?.status()??null;row.final_url=page.url();row.redirects=[];
    let request=response?.request();
    while(request?.redirectedFrom()){row.redirects.unshift({from:request.redirectedFrom().url(),to:request.url()});request=request.redirectedFrom();}
    if(new URL(page.url()).hostname.replace(/^www\./,'')!=='davila.cl')throw Error('unreviewed redirect host');
    const html=await page.content();if(Buffer.byteLength(html)>6*1024*1024)throw Error('response_size_limit');
    row.dom_sha256=crypto.createHash('sha256').update(html).digest('hex');
    row.challenge_detected=/Just a moment|cf-chl-|captcha|Access denied|403 Forbidden/i.test(html);
    row.file=path.join(dir,row.dom_sha256+'.html.gz');fs.writeFileSync(row.file,zlib.gzipSync(html));
   }catch(error){row.error=error.name;row.detail=error.message.slice(0,200);}
   results.push(row);fs.writeFileSync(path.join(dir,'capture.json'),JSON.stringify({target_count:targets.length,results}));
  }
  await page.close();
 }
 await Promise.all([worker(),worker()]);await browser.close();
})().catch(error=>{process.stderr.write(error.message+'\n');process.exitCode=1;});
