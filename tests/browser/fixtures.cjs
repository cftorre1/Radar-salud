// Browser specs assert editorial fixtures audited on a fixed date (sanction
// windows, 90-day filters, weekly freshness). Pin the page clock to that date
// so the suite does not decay as calendar days pass. The published snapshot is
// built separately with the real date; see .github/workflows/qa.yml.
const base=require('@playwright/test');
const FIXTURE_AS_OF=process.env.ALICANTO_FIXTURE_AS_OF||'2026-10-12';
const test=base.test.extend({
  page:async({page},use)=>{
    await page.clock.setFixedTime(new Date(`${FIXTURE_AS_OF}T12:00:00-03:00`));
    await use(page);
  },
});
module.exports={...base,test,FIXTURE_AS_OF};
