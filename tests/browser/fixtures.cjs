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
// The period selector lives inside 'Filtrar u ordenar' (Dirección 25-oct): open it first when closed.
async function selectPeriod(page,value){const details=page.locator('#filterDetails');if(!(await details.evaluate(el=>el.open)))await details.locator('summary').click();await page.locator('#period').selectOption(value)}
// Below 1000px the lanes live in the "N pendientes ▾" menu (review N1 of PR #72, design B §6):
// open it first when the lane is not visible.
async function selectLane(page,lane){const target=page.locator(`[data-lane="${lane}"]`);await target.waitFor({state:'attached'});if(!(await target.isVisible()))await page.locator('#laneToggle').click();await target.click()}
module.exports={...base,test,FIXTURE_AS_OF,selectPeriod,selectLane};
