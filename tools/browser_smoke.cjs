/* Optional real-browser check: requires playwright and its Chromium executable. */
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const modulePaths=[process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES||'',process.cwd()];
let chromium;
try {({chromium}=require(require.resolve('playwright',{paths:modulePaths})));}
catch {console.error('Install Playwright and Chromium in your development environment, then rerun this optional check.');process.exit(2);}
const root=path.resolve(__dirname,'..');
const artifacts=path.join(root,'.delivery/runtime/browser');
fs.mkdirSync(artifacts,{recursive:true});
const env={...process.env,TMPDIR:path.join(artifacts,'tmp')};
fs.mkdirSync(env.TMPDIR,{recursive:true});
for(const key of ['WISDOM_PROVIDER_URL','WISDOM_MODEL','WISDOM_API_KEY'])delete env[key];
const child=spawn('python',['-m','wisdom','--db',path.join(artifacts,'test-'+Date.now()+'.db'),'--raw-dir',path.join(artifacts,'raw'),'serve','--port','0'],{cwd:root,env,stdio:['ignore','pipe','inherit']});
const base=new Promise((resolve,reject)=>{
 const timeout=setTimeout(()=>reject(Error('Local server did not start')),10000);
 child.stdout.on('data',data=>{const match=String(data).match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timeout);resolve(match[0]);}});
 child.on('exit',code=>reject(Error('Server exited: '+code)));
});
(async()=>{
 let browser;
 try{
  const url=await base;browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await page.waitForSelector('#connection-dot.online');
  await page.locator('#nav [data-view=sources]').click();
  const form=page.locator('#source-form');
  await form.locator('[name=title]').fill('Synthetic browser fixture');
  await form.locator('[name=source_family]').fill('synthetic-browser-only');
  await form.locator('[name=text]').fill('  A feedback practice may help under stable conditions. It does not always work.\n');
  await form.locator('[name=rights_confirmed]').check();
  await form.locator('button[type=submit]').click();
  await page.locator('#source-list .record-title').filter({hasText:'Synthetic browser fixture'}).waitFor();
  await page.locator('#source-list').getByRole('button',{name:'Analyze',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#claim-count').textContent!=='0');
  await page.locator('#nav [data-view=atlas]').click();
  await page.locator('#claim-list').getByRole('button',{name:'Review',exact:true}).first().click();
  await page.locator('#detail-dialog').waitFor();
  await page.locator('.review-form [name=reviewer]').fill('browser fixture reviewer');
  await page.locator('.review-form button[type=submit]').click();
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('#detail-body pre')).some(x=>x.textContent==='accepted'));
  await page.locator('#close-detail').click();
  await page.locator('#nav [data-view=discovery]').click();
  const problem=page.locator('#problem-form');
  await problem.locator('[name=title]').fill('Synthetic feedback problem');
  await problem.locator('[name=description]').fill('Repeated feedback causes oscillation.');
  await problem.locator('[name=desired_state]').fill('Stable feedback');
  await problem.locator('[name=maintaining_force]').fill('One review cadence');
  await problem.locator('button').click();
  await page.locator('#problem-list .record-title').filter({hasText:'Synthetic feedback problem'}).waitFor();
  await page.locator('#problem-list').getByRole('button',{name:'Forge candidates',exact:true}).click();
  await page.locator('#forge-results-panel').waitFor();
  await page.locator('#nav [data-view=overview]').click();
  await page.screenshot({path:path.join(artifacts,'desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(artifacts,'mobile.png'),fullPage:true});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Horizontal overflow at mobile width.');
  if(errors.length)throw Error(errors.join('\n'));
  console.log('Browser source intake, analysis, human review, no-match forge and desktop/mobile layout checks passed.');
 }finally{if(browser)await browser.close();child.kill('SIGTERM');}
})().catch(error=>{console.error(error.message);child.kill('SIGTERM');process.exitCode=1;});

