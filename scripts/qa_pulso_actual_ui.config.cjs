const {defineConfig}=require('@playwright/test');
const path=require('node:path');
const root=process.env.PULSO_QA_ROOT||path.resolve(__dirname,'..');
const web=process.env.PULSO_QA_WEB||path.join(root,'web');
const output=process.env.PULSO_QA_RESULTS||path.join(root,'artifacts/pulso-actual-ui');
const url=process.env.PULSO_QA_URL||'http://127.0.0.1:8771';
const quote=value=>"'"+String(value).replace(/'/g,"'\\''")+"'";
module.exports=defineConfig({
 testDir:__dirname,testMatch:'qa_pulso_actual_ui.spec.cjs',timeout:30000,retries:0,workers:2,
 outputDir:path.join(output,'results'),reporter:[['list'],['json',{outputFile:path.join(output,'browser.json')}]],
 use:{baseURL:url,launchOptions:process.env.PULSO_QA_CHROMIUM?{executablePath:process.env.PULSO_QA_CHROMIUM}:{},screenshot:'only-on-failure',trace:'retain-on-failure'},
 webServer:process.env.PULSO_QA_URL?undefined:{command:`${quote(process.env.PULSO_QA_PYTHON||'python')} -m http.server 8771 --directory ${quote(web)}`,url,reuseExistingServer:false},
 projects:[{name:'desktop',use:{viewport:{width:1440,height:900}}},{name:'mobile',use:{viewport:{width:390,height:844},isMobile:true,hasTouch:true}}],
});
