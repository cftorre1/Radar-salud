const {defineConfig}=require('@playwright/test');
module.exports=defineConfig({
  testDir:'./tests/browser',timeout:30000,retries:0,
  reporter:[['list'],['json',{outputFile:'artifacts/browser.json'}]],
  use:{baseURL:process.env.STAGING_URL||'http://127.0.0.1:8765',screenshot:'only-on-failure',trace:'retain-on-failure'},
  webServer:process.env.STAGING_URL?undefined:{command:'python -m http.server 8765 --directory web',url:'http://127.0.0.1:8765',reuseExistingServer:false},
  projects:[{name:'desktop',use:{viewport:{width:1440,height:900}}},{name:'mobile',use:{viewport:{width:390,height:844},isMobile:true,hasTouch:true}}]
});
