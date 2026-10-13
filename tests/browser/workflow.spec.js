import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs';
fs.mkdirSync('evidence/screenshots',{recursive:true});

test.afterEach(async ({page}) => {
  // Polling can still be inside route.fetch/json when assertions finish.
  // Drain those handlers before Playwright disposes the request context.
  await page.unrouteAll({behavior:'wait'});
});

async function accessibility(page) {
  // This app has no frames. Scan the actual page directly so a separate
  // analysis page cannot use a different system theme than emulateMedia.
  expect(page.frames()).toHaveLength(1);
  return new AxeBuilder({page}).setLegacyMode(true).analyze();
}

test('one workspace selects input, keeps settings across setup, and returns a real queued copy', async ({page}) => {
  await signIn(page);
  await expect.poll(async()=>page.locator('#connection').textContent()).toMatch(/connected/i);
  await expect(page.getByRole('navigation')).toHaveCount(0);
  await expect(page.getByRole('combobox')).toHaveCount(3);
  await expect(page.getByRole('button',{name:'Add to queue',exact:true})).toBeDisabled();
  const icon=await page.request.get(await page.locator('link[rel=icon]').getAttribute('href'));
  expect(icon.ok()).toBeTruthy();
  expect(await icon.text()).toContain('cx="21" cy="20.3" r="4.5" fill="#14b8a6"');
  const input=page.getByRole('region',{name:'Input',exact:true});
  const output=page.getByRole('region',{name:'Output queue',exact:true});
  const settings=page.getByRole('region',{name:'Upscaling settings',exact:true});
  const source=page.getByRole('button',{name:'A clearer picture.mkv',exact:true});
  await source.click();
  await expect(source).toHaveAttribute('aria-pressed','true');
  await page.getByRole('combobox',{name:'Output size',exact:true}).click();
  await page.getByRole('option',{name:'Three times the size (3×)',exact:true}).click();
  await moreOptions(page);
  await page.getByLabel('Save copies to').fill('simple-workspace');
  await navigate(page,'Processing');
  await page.getByRole('button',{name:'Back to videos',exact:true}).click();
  await expect(source).toHaveAttribute('aria-pressed','true');
  await expect(page.getByLabel('Save copies to')).toHaveValue('simple-workspace');
  await expect(page.getByRole('combobox',{name:'Output size',exact:true})).toContainText('Three times');
  await page.getByRole('button',{name:'More options',exact:true}).click();
  await expect(page.getByRole('combobox')).toHaveCount(3);
  const [response]=await Promise.all([
    page.waitForResponse(r=>r.url().endsWith('/api/jobs') && r.request().method()==='POST'),
    page.getByRole('button',{name:'Add to queue',exact:true}).click(),
  ]);
  expect(response.ok()).toBeTruthy();
  const job=await response.json();
  expect(job.recipe).toMatchObject({engine:'resize',scale:3,preview_seconds:0,output_directory:'simple-workspace'});
  const download=output.locator(`[data-job-id="${job.id}"]`).getByRole('link',{name:'Download copy',exact:true});
  await expect(download).toBeVisible({timeout:30000});
  expect((await page.request.get(await download.getAttribute('href'))).ok()).toBeTruthy();
  await expect(source).toHaveAttribute('aria-pressed','false');
  for(const [width,height,mode] of [[1440,1000,'light'],[768,1024,'dark'],[390,844,'dark']]) {
    await page.setViewportSize({width,height});
    await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    const {left,right,below}=await page.evaluate(()=>({left:document.querySelector('[aria-label="Input"]').getBoundingClientRect().toJSON(),right:document.querySelector('[aria-label="Output queue"]').getBoundingClientRect().toJSON(),below:document.querySelector('[aria-label="Upscaling settings"]').getBoundingClientRect().toJSON()}));
    expect(below.y).toBeGreaterThan(Math.max(left.y+left.height,right.y+right.height));
    if(width>=768) expect(right.x).toBeGreaterThan(left.x+left.width);
    else expect(right.y).toBeGreaterThan(left.y+left.height);
    expect((await accessibility(page)).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    await page.evaluate(()=>scrollTo(0,0));
    if(process.env.POPCORN_CAPTURE_UI==='1') await page.screenshot({path:`evidence/simple-workspace-20261013/final-${width}-${mode}.png`,fullPage:true,animations:'disabled'});
  }
});

test('VSR controls keep exact dimensions and verified quality intent (UI fixture; no GPU execution)', async ({page}) => {
  let ready=true, submitted;
  await page.route('**/api/state', async route => {
    const response=await route.fetch();
    if(!response.ok()) {await route.fulfill({response});return;}
    const state=await response.json();
    state.workers.push({id:'vsr-ui-fixture',name:'VSR controls fixture',online:true,revoked:false,scratch:{path:'/scratch',free_bytes:1e9},capabilities:{
      engines:['rtx-vsr'],encoders:['h264_nvidia','hevc_nvidia','av1_nvidia'],device:'UI fixture · no GPU processing',platform:'Linux',architecture:'x86_64',notes:{},
      rtx_vsr:ready?{qualities:[1,2,3,4],strength:true,custom_size:true,codecs:['h264','hevc','av1'],lossless:true}:{},
      dlss_frame_generation:{upscalers:['rtx-vsr'],settings:[['auto','high']],maximum_factor:6},
      rtx_hdr:{pipelines:[['rtx-vsr',false,'hevc'],['rtx-vsr',true,'hevc'],['rtx-vsr',false,'av1'],['rtx-vsr',true,'av1']]},
    }});
    state.jobs.push({id:'vsr-summary-fixture',path:'VSR configuration fixture.mkv',status:'queued',stage:'UI fixture',progress:0,recipe:{engine:'rtx-vsr',codec:'av1',scale:2,vsr_quality:4,vsr_strength:.6,output_width:1920,output_height:1080,preview_seconds:5}});
    await route.fulfill({response,json:state});
  });
  await page.route('**/api/jobs', async route => {
    submitted=route.request().postDataJSON();
    await route.fulfill({status:400,json:{detail:'VSR configuration fixture: no GPU job was submitted.'}});
  });
  await signIn(page);
  await navigate(page,'Library');
  await page.getByRole('button',{name:'A clearer picture.mkv',exact:true}).click();
  await page.getByRole('combobox',{name:'Processing device',exact:true}).click();
  await page.getByRole('option',{name:'VSR controls fixture',exact:true}).click();
  await page.getByRole('combobox',{name:'Enhancement',exact:true}).click();
  await page.getByRole('option',{name:'RTX Video Super Resolution',exact:true}).click();
  await page.getByRole('combobox',{name:'VSR quality',exact:true}).click();
  await page.getByRole('option',{name:'Level 4 · Ultra',exact:true}).click();
  await page.getByRole('combobox',{name:'Output size',exact:true}).click();
  await page.getByRole('option',{name:'Custom dimensions',exact:true}).click();
  await page.getByRole('spinbutton',{name:'Output width',exact:true}).fill('1921');
  await page.getByRole('spinbutton',{name:'Output width',exact:true}).press('Tab');
  await expect(page.getByText('Check the output dimensions',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Preview 5 seconds',exact:true})).toBeDisabled();
  await page.getByRole('spinbutton',{name:'Output width',exact:true}).fill('1920');
  await page.getByRole('spinbutton',{name:'Output width',exact:true}).press('Tab');
  await moreOptions(page);
  await page.getByRole('spinbutton',{name:'VSR strength',exact:true}).fill('60');
  await page.getByRole('spinbutton',{name:'VSR strength',exact:true}).press('Tab');
  await page.getByRole('combobox',{name:'Video format',exact:true}).click();
  await page.getByRole('option',{name:'AV1 · newer players',exact:true}).click();
  await page.getByLabel('Save copies to').fill('vsr/movies');
  await page.waitForTimeout(3200);
  await expect(page.getByRole('combobox',{name:'VSR quality',exact:true})).toContainText('Level 4');
  await expect(page.getByRole('spinbutton',{name:'VSR strength',exact:true})).toHaveValue('60');
  for(const [width,height,mode] of [[1440,1100,'light'],[390,844,'dark']]) {
    await page.setViewportSize({width,height});
    await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    await page.evaluate(()=>scrollTo(0,0));
    expect((await accessibility(page)).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    for(const control of await page.getByRole('spinbutton').all()) expect((await control.boundingBox()).height).toBeGreaterThanOrEqual(44);
  }
  ready=false;
  await expect(page.getByText('RTX Video settings are unavailable',{exact:true})).toBeVisible({timeout:6000});
  await expect(page.getByRole('button',{name:'Preview 5 seconds',exact:true})).toBeDisabled();
  await expect(page.getByRole('spinbutton',{name:'Output width',exact:true})).toHaveValue('1920');
  await expect(page.getByRole('spinbutton',{name:'VSR strength',exact:true})).toHaveValue('60');
  ready=true;
  await expect(page.getByRole('button',{name:'Preview 5 seconds',exact:true})).toBeEnabled({timeout:6000});
  await page.getByRole('checkbox',{name:'DLSS frame generation · experimental',exact:true}).check();
  await page.getByRole('checkbox',{name:'RTX Video HDR · experimental',exact:true}).check();
  await page.getByRole('button',{name:'Preview 5 seconds',exact:true}).click();
  expect(submitted.recipe).toMatchObject({engine:'rtx-vsr',vsr_quality:4,vsr_strength:.6,output_width:1920,output_height:1080,codec:'av1',encoder:'nvidia',frame_generation:true,hdr:true,preview_seconds:5,output_directory:'vsr/movies'});
  await navigate(page,'Queue');
  await expect(page.locator('#jobs')).toContainText('VSR quality: Level 4 · Ultra · Strength: 60%');
  await expect(page.locator('#jobs')).toContainText('1920 × 1080 px');
});

test('HDR controls preserve intent and require verified exports (UI fixture; no GPU execution)', async ({page}) => {
  let ready=true, submitted;
  await page.route('**/api/state', async route => {
    const response=await route.fetch();
    if(!response.ok()) {await route.fulfill({response});return;}
    const state=await response.json();
    state.workers.push({id:'hdr-ui-fixture',name:'HDR controls fixture',online:true,revoked:false,scratch:{path:'/scratch',free_bytes:1e9},capabilities:{
      engines:['resize'],encoders:['h264_nvidia','hevc_nvidia','av1_nvidia'],device:'UI fixture · no GPU processing',platform:'Linux',architecture:'x86_64',notes:{},
      rtx_hdr:{pipelines:ready?[['resize',false,'hevc'],['resize',false,'av1']]:[]},
    }});
    state.jobs.push({id:'hdr-summary-fixture',path:'HDR configuration fixture.mkv',status:'queued',stage:'UI fixture',progress:0,recipe:{engine:'resize',codec:'hevc',scale:2,hdr:true,hdr_luminance:1000,preview_seconds:5}});
    await route.fulfill({response,json:state});
  });
  await page.route('**/api/jobs', async route => {
    submitted=route.request().postDataJSON();
    await route.fulfill({status:400,json:{detail:'HDR configuration fixture: no GPU job was submitted.'}});
  });
  await signIn(page);
  await navigate(page,'Library');
  await page.getByRole('button',{name:'A clearer picture.mkv',exact:true}).click();
  await page.getByRole('combobox',{name:'Processing device',exact:true}).click();
  await page.getByRole('option',{name:'Local CPU worker',exact:true}).click();
  await expect(page.getByRole('checkbox',{name:'RTX Video HDR · experimental',exact:true})).toBeDisabled();
  await page.getByRole('combobox',{name:'Processing device',exact:true}).click();
  await page.getByRole('option',{name:'HDR controls fixture',exact:true}).click();
  await page.getByRole('checkbox',{name:'RTX Video HDR · experimental',exact:true}).check();
  await expect(page.getByRole('combobox',{name:'Video format',exact:true})).toContainText('H.265');
  await page.getByRole('combobox',{name:'Video format',exact:true}).click();
  await expect(page.getByRole('option',{name:'H.264 · broad compatibility',exact:true})).toHaveAttribute('aria-disabled','true');
  await page.getByRole('option',{name:'AV1 · newer players',exact:true}).click();
  await moreOptions(page);
  for(const [label,value] of [['Peak brightness','1000'],['HDR contrast','85'],['HDR saturation','110'],['Midtone brightness','45']]) {
    await page.getByRole('spinbutton',{name:label,exact:true}).fill(value);
    await page.getByRole('spinbutton',{name:label,exact:true}).press('Tab');
  }
  await page.getByRole('checkbox',{name:'Reduce banding in HDR',exact:true}).uncheck();
  await page.getByLabel('Save copies to').fill('hdr/movies');
  await page.waitForTimeout(3200);
  await expect(page.getByRole('spinbutton',{name:'Peak brightness',exact:true})).toHaveValue('1000');
  await page.getByRole('button',{name:'Preview 5 seconds',exact:true}).click();
  expect(submitted.recipe).toMatchObject({engine:'resize',hdr:true,codec:'av1',encoder:'nvidia',hdr_luminance:1000,hdr_contrast:85,hdr_saturation:110,hdr_middle_gray:45,hdr_debanding:false,preview_seconds:5,output_directory:'hdr/movies'});
  for(const [width,height,mode] of [[1440,1100,'light'],[390,844,'dark']]) {
    await page.setViewportSize({width,height});
    await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    await page.evaluate(()=>scrollTo(0,0));
    expect((await accessibility(page)).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    for(const control of await page.getByRole('spinbutton').all()) {
      expect((await control.boundingBox()).height).toBeGreaterThanOrEqual(44);
    }
  }
  ready=false;
  await expect(page.getByText('HDR is unavailable',{exact:true})).toBeVisible({timeout:6000});
  await expect(page.getByRole('checkbox',{name:'RTX Video HDR · experimental',exact:true})).toBeChecked();
  await expect(page.getByRole('button',{name:'Preview 5 seconds',exact:true})).toBeDisabled();
  await expect(page.getByRole('spinbutton',{name:'Peak brightness',exact:true})).toHaveValue('1000');
  ready=true;
  await expect(page.getByRole('button',{name:'Preview 5 seconds',exact:true})).toBeEnabled({timeout:6000});
  await expect(page.getByRole('combobox',{name:'Video format',exact:true})).toContainText('AV1');
  await navigate(page,'Queue');
  await expect(page.locator('#jobs')).toContainText('RTX Video HDR · 10-bit · Peak brightness: 1000 nits');
});

test('DLSS controls obey verified combinations (UI fixture; no GPU execution)', async ({page}) => {
  // Browser-only contract data; real GPU acceptance runs separately on Spark.
  await page.route('**/api/state', async route => {
    const response=await route.fetch();
    if (!response.ok()) { await route.fulfill({response}); return; }
    const state=await response.json();
    state.workers.push({id:'dlss-ui-fixture',name:'DLSS controls fixture',online:true,revoked:false,scratch:{path:'/scratch',free_bytes:1e9},capabilities:{
      engines:['dlss-sr'],encoders:['h264_nvidia'],device:'UI fixture',platform:'Linux',architecture:'aarch64',notes:{},
      dlss_sr:{settings:[['quality','k'],['performance','m']],temporal_qualities:['high','low']},
    }});
    state.jobs.push({id:'dlss-summary-fixture',path:'Configuration fixture.mkv',status:'queued',stage:'UI fixture',progress:0,recipe:{engine:'dlss-sr',codec:'hevc',scale:2,dlss_mode:'quality',dlss_preset:'k',temporal_quality:'low',preview_seconds:5}});
    await route.fulfill({response,json:state});
  });
  let submitted;
  await page.route('**/api/jobs', async route => {
    submitted=route.request().postDataJSON();
    await route.fulfill({status:400,json:{detail:'Configuration fixture: no GPU job was submitted.'}});
  });
  await signIn(page);
  await navigate(page,'Library');
  await page.getByRole('button',{name:'A clearer picture.mkv'}).click();
  await page.getByRole('combobox',{name:'Processing device',exact:true}).click();
  await page.getByRole('option',{name:'DLSS controls fixture',exact:true}).click();
  await expect(page.getByRole('combobox',{name:'DLSS mode',exact:true})).toBeVisible();
  await page.getByRole('combobox',{name:'DLSS mode',exact:true}).click();
  await page.getByRole('option',{name:'Quality · 1.5×',exact:true}).click();
  await moreOptions(page);
  await expect(page.getByRole('combobox',{name:'DLSS model preset',exact:true})).toContainText('K · fine detail');
  await page.getByRole('combobox',{name:'DLSS model preset',exact:true}).click();
  await expect(page.getByRole('option',{name:'M · Performance default',exact:true})).toHaveCount(0);
  await page.keyboard.press('Escape');
  await page.getByRole('combobox',{name:'Motion estimation',exact:true}).click();
  await page.getByRole('option',{name:'Fast · less accurate',exact:true}).click();
  await page.getByLabel('Save copies to').fill('dlss/quality');
  await page.waitForTimeout(2200);
  await expect(page.getByRole('combobox',{name:'DLSS mode',exact:true})).toContainText('Quality');
  await page.getByRole('button',{name:'Preview 5 seconds',exact:true}).click();
  await expect(page.getByText('Configuration fixture: no GPU job was submitted.',{exact:true})).toBeVisible();
  expect(submitted.recipe).toMatchObject({engine:'dlss-sr',dlss_mode:'quality',dlss_preset:'k',temporal_quality:'low',codec:'h264',encoder:'nvidia',preview_seconds:5,output_directory:'dlss/quality'});
  for (const [width,height,mode] of [[1440,1100,'light'],[390,844,'dark']]) {
    await page.setViewportSize({width,height});
    await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    await page.evaluate(()=>scrollTo(0,0));
    expect((await accessibility(page)).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  }
  await navigate(page,'Queue');
  await expect(page.locator('#jobs')).toContainText('H.265 / HEVC');
  await expect(page.locator('#jobs')).toContainText('Preset: K · Motion estimation: Fast');
  for (const [width,height,mode] of [[1440,1100,'light'],[390,844,'dark']]) {
    await page.setViewportSize({width,height});
    await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    await page.evaluate(()=>scrollTo(0,0));
    expect((await accessibility(page)).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  }
});


test('frame generation is independent, verified, and saved with the codec (UI fixture; no GPU execution)', async ({page}) => {
  let available=true;
  await page.route('**/api/state', async route => {
    const response=await route.fetch();
    if (!response.ok()) { await route.fulfill({response}); return; }
    const state=await response.json();
    state.workers.push({id:'fg-ui-fixture',name:'Frame-generation controls fixture',online:true,revoked:false,scratch:{path:'/scratch',free_bytes:1e9},capabilities:{
      engines:['resize','dlss-sr'],encoders:['h264_nvidia','hevc_nvidia','av1_nvidia'],device:'UI fixture',platform:'Linux',architecture:'aarch64',notes:{},
      dlss_sr:{settings:[['quality','k']],temporal_qualities:['high']},
      dlss_frame_generation:available?{maximum_factor:6,upscalers:['resize','dlss-sr'],settings:[['auto','high'],['native','low'],['cascade','medium']]}:{},
    }});
    state.jobs.push({id:'fg-summary-fixture',path:'Cadence fixture.mkv',status:'queued',stage:'UI fixture',progress:0,recipe:{engine:'resize',codec:'hevc',scale:1,frame_generation:true,frame_rate:'480',frame_generation_mode:'cascade',frame_generation_quality:'medium',preview_seconds:5}});
    await route.fulfill({response,json:state});
  });
  let submitted;
  await page.route('**/api/jobs', async route => {
    submitted=route.request().postDataJSON();
    await route.fulfill({status:400,json:{detail:'Configuration fixture: no GPU job was submitted.'}});
  });
  await signIn(page);
  await navigate(page,'Library');
  await page.getByRole('button',{name:'A clearer picture.mkv'}).click();
  const workerNames=(await (await page.request.get('/api/state')).json()).workers.map(w=>w.name);
  await page.getByRole('combobox',{name:'Processing device',exact:true}).click();
  await page.getByRole('option',{name:workerNames[0],exact:true}).click();
  const toggle=page.getByRole('checkbox',{name:'DLSS frame generation · experimental',exact:true});
  await expect(toggle).toBeDisabled();
  await page.getByRole('combobox',{name:'Processing device',exact:true}).click();
  await page.getByRole('option',{name:'Frame-generation controls fixture',exact:true}).click();
  await page.getByRole('combobox',{name:'Enhancement',exact:true}).click();
  await page.getByRole('option',{name:'Conventional resizing',exact:true}).click();
  await expect(toggle).toBeEnabled();
  await toggle.check();
  await page.getByRole('combobox',{name:'Output size',exact:true}).click();
  await page.getByRole('option',{name:'Keep source size (1×)',exact:true}).click();
  await page.getByRole('combobox',{name:'Frame rate',exact:true}).click();
  for(const rate of ['23.976','25','29.97','30','50','59.94','60','90','119.88','120','144','165','180','240','360','480']) {
    await expect(page.getByRole('option',{name:`${rate} fps`,exact:true})).toBeAttached();
  }
  await page.getByRole('option',{name:'480 fps',exact:true}).click();
  await page.getByRole('combobox',{name:'Video format',exact:true}).click();
  await page.getByRole('option',{name:'H.265 / HEVC · smaller files',exact:true}).click();
  await moreOptions(page);
  await page.getByRole('combobox',{name:'Frame-generation mode',exact:true}).click();
  await page.getByRole('option',{name:'Cascade · multiple NVIDIA passes',exact:true}).click();
  await expect(page.getByRole('combobox',{name:'Frame-generation motion',exact:true})).toContainText('Balanced');
  await expect(page.getByRole('combobox',{name:'Encoding hardware',exact:true})).toContainText('NVIDIA GPU');
  await expect(page.getByRole('checkbox',{name:'Smooth motion to 60 fps',exact:true})).toBeDisabled();
  await page.waitForTimeout(2200);
  await expect(page.getByRole('combobox',{name:'Frame rate',exact:true})).toContainText('480 fps');
  for (const [width,height,mode] of [[1440,1100,'light'],[390,844,'dark']]) {
    await page.setViewportSize({width,height});
    await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    await page.evaluate(()=>scrollTo(0,0));
    expect((await accessibility(page)).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  }
  await page.getByRole('button',{name:'Preview 5 seconds',exact:true}).click();
  await expect(page.getByText('Configuration fixture: no GPU job was submitted.',{exact:true})).toBeVisible();
  expect(submitted.recipe).toMatchObject({engine:'resize',scale:1,frame_generation:true,frame_rate:'480',frame_generation_mode:'cascade',frame_generation_quality:'medium',codec:'hevc',encoder:'nvidia',interpolate:false,preview_seconds:5});
  available=false;
  await expect(page.getByText('Your selection is kept. Choose a compatible worker or turn off frame generation to continue.',{exact:true})).toBeVisible({timeout:5000});
  await expect(toggle).toBeChecked();
  await expect(page.getByRole('button',{name:'Preview 5 seconds',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Add to queue',exact:true})).toBeDisabled();
  for (const [width,height,mode] of [[1440,1100,'light'],[390,844,'dark']]) {
    await page.setViewportSize({width,height});
    await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    await page.evaluate(()=>scrollTo(0,0));
    expect((await accessibility(page)).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  }
  await toggle.uncheck();
  await expect(toggle).not.toBeChecked();
  await navigate(page,'Queue');
  await expect(page.locator('#jobs')).toContainText('DLSS frame generation: 480 fps · Cascade · Motion: Balanced');
  for (const [width,height,mode] of [[1440,1100,'light'],[390,844,'dark']]) {
    await page.setViewportSize({width,height});
    await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    await page.evaluate(()=>scrollTo(0,0));
    expect((await accessibility(page)).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  }
});

async function moreOptions(page) {
  const control=page.getByRole('button',{name:'More options',exact:true});
  if(await control.getAttribute('aria-expanded')!=='true') await control.click();
}
async function navigate(page, name) {
  await expect(page.locator('#connection')).toBeVisible();
  if(name==='Processing') {
    const setup=page.getByRole('button',{name:'Devices & storage',exact:true});
    if(await setup.isVisible()) await setup.click();
  } else {
    const back=page.getByRole('button',{name:'Back to videos',exact:true});
    if(await back.isVisible()) await back.click();
    if(name==='Library') await moreOptions(page);
    if(name==='Queue') for(const details of await page.locator('#jobs').getByRole('button',{name:'Details',exact:true}).all()) {
      if(await details.getAttribute('aria-expanded')!=='true') await details.click();
    }
  }
}

async function signIn(page) {
  await page.goto('/');
  await page.getByLabel('Access key').fill('local-test-only-access-key-12345');
  await page.getByRole('button',{name:'Open Popcorn SR'}).click();
  await expect(page.getByRole('heading',{name:'Upscale your videos'})).toBeVisible();
}

test('paired device shows checking, ready and failure without exposing stale support (UI fixture)', async ({page}) => {
  let phase='checking';
  const errors=[];
  page.on('pageerror', error=>errors.push(error.message));
  await page.route('**/api/state', async route=>{
    const response=await route.fetch();
    if(!response.ok()){await route.fulfill({response});return;}
    const state=await response.json();
    // Stale encoder data intentionally tests the initialization gate. This is
    // display evidence; real pairing and CPU/GPU acceptance run separately.
    state.workers=[{id:'pairing-ui-fixture',name:'Processing computer',online:true,revoked:false,
      scratch:{path:'/scratch/external/temporary-video-files',free_bytes:1e9,available:phase!=='failed'},
      capabilities:{initialization:phase,initialization_error:'Temporary drive is unavailable. Reconnect it and restart the worker.',
        engines:['resize'],encoders:['h264_cpu','hevc_cpu','av1_cpu'],device:phase==='ready'?'CPU worker':'',
        platform:'Linux',architecture:'aarch64',notes:{}}}];
    await route.fulfill({response,json:state});
  });
  await signIn(page);
  await navigate(page,'Processing');
  const card=page.getByRole('article',{name:'Processing computer',exact:true});
  await expect(card.getByText('Checking support',{exact:true})).toBeVisible();
  await expect(card).toContainText('This can take several minutes. Jobs wait until checks finish.');
  await expect(card.getByText('Verified encoding',{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Connect a worker',exact:true}).click();
  await expect(page.getByText(/The device appears as soon as it pairs/)).toBeVisible();
  for(const [width,height,mode] of [[1440,1100,'light'],[390,844,'dark']]){
    await page.setViewportSize({width,height});
    await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    await page.evaluate(()=>scrollTo(0,0));
    expect((await accessibility(page)).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  }
  await navigate(page,'Library');
  await page.getByRole('button',{name:'A clearer picture.mkv'}).click();
  const selector=page.getByRole('combobox',{name:'Processing device',exact:true});
  await selector.click();
  await page.getByRole('option',{name:'Processing computer (checking support)',exact:true}).click();
  await expect(page.getByText('Support checks are running. Options become available when they finish.',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Preview 5 seconds',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Add to queue',exact:true})).toBeDisabled();
  await page.getByLabel('Save copies to').fill('previews/pairing');
  phase='ready';
  await expect(selector).toContainText('Processing computer');
  await expect(page.getByRole('button',{name:'Preview 5 seconds',exact:true})).toBeEnabled();
  await expect(selector).not.toContainText('checking support');
  await expect(page.getByLabel('Save copies to')).toHaveValue('previews/pairing');
  await page.getByRole('combobox',{name:'Video format',exact:true}).click();
  await page.getByRole('option',{name:'H.265 / HEVC · smaller files',exact:true}).click();
  phase='failed';
  await expect(selector).toContainText('checks failed');
  await expect(page.getByRole('button',{name:'Preview 5 seconds',exact:true})).toBeDisabled();
  await expect(page.getByLabel('Save copies to')).toHaveValue('previews/pairing');
  phase='ready';
  await expect(page.getByRole('button',{name:'Preview 5 seconds',exact:true})).toBeEnabled();
  await expect(page.getByRole('combobox',{name:'Video format',exact:true})).toContainText('H.265 / HEVC');
  phase='failed';
  await navigate(page,'Processing');
  await expect(card.getByText('Checks failed',{exact:true})).toBeVisible();
  await expect(card).toContainText('Reconnect it and restart the worker.');
  await expect(card.getByText('Unavailable',{exact:true})).toBeVisible();
  await expect(card.getByText('Verified encoding',{exact:true})).toHaveCount(0);
  for(const [width,height,mode] of [[1440,1100,'light'],[390,844,'dark']]){
    await page.setViewportSize({width,height});
    await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    await page.evaluate(()=>scrollTo(0,0));
    expect((await accessibility(page)).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  }
  expect(errors).toEqual([]);
});

test('desktop preview completes on a real worker; responsive light/dark views pass accessibility', async ({page}) => {
  const errors = [];
  await page.addInitScript(() => {
    window.policyViolations = [];
    document.addEventListener('securitypolicyviolation', event => window.policyViolations.push(event.violatedDirective));
  });
  page.on('pageerror', error => errors.push(error.message));
  await signIn(page);
  await expect.poll(async () => page.locator('#connection').textContent()).toMatch(/connected/i);
  await page.evaluate(() => scrollTo(0,0));
  await navigate(page,'Library');
  await page.getByRole('button',{name:'A clearer picture.mkv'}).click();
  const workers = (await (await page.request.get('/api/state')).json()).workers;
  await page.getByRole('combobox',{name:'Processing device',exact:true}).click();
  await page.getByRole('option',{name:workers[0].name,exact:true}).click();
  await page.getByRole('combobox',{name:'Output size',exact:true}).click();
  await page.getByRole('option',{name:'Twice the size (2×)',exact:true}).click();
  await page.getByLabel('Save copies to').fill('previews/check');
  // A real worker heartbeat must not reset a user's edits.
  await page.waitForTimeout(3200);
  await expect(page.getByLabel('Save copies to')).toHaveValue('previews/check');
  await expect(page.getByRole('combobox',{name:'Processing device',exact:true})).toContainText(workers[0].name);
  await page.evaluate(() => scrollTo(0,0));
  await page.getByRole('button',{name:'Preview 5 seconds'}).click();
  await expect(page.getByRole('heading',{name:'Output queue',exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'Download preview'})).toBeVisible({timeout:30000});
  const download = await page.request.get(await page.getByRole('link',{name:'Download preview'}).getAttribute('href'));
  expect(download.ok()).toBeTruthy();
  expect((await download.body()).length).toBeGreaterThan(1000);
  await page.evaluate(() => scrollTo(0,0));
  const [continued] = await Promise.all([
    page.waitForResponse(r => r.url().endsWith('/full') && r.request().method() === 'POST'),
    page.locator('#jobs').getByRole('button',{name:'Enhance full video'}).click()
  ]);
  expect(continued.ok()).toBeTruthy();
  const full = await continued.json();
  expect(full.recipe.preview_seconds).toBe(0);
  expect(full.recipe.output_directory).toBe('previews/check');
  expect(full.recipe.scale).toBe(2);
  expect(full.target).toBe(workers[0].id);
  const completed = page.locator(`[data-job-id="${full.id}"]`).getByRole('link',{name:'Download copy',exact:true});
  await expect(completed).toBeVisible({timeout:30000});
  const finished = (await (await page.request.get('/api/state')).json()).jobs.find(j => j.id === full.id);
  expect(finished.status).toBe('completed');
  expect(finished.result.duration).toBeGreaterThan(5.5);
  expect(finished.result.audio_streams).toBe(1);
  expect((await accessibility(page)).violations).toEqual([]);
  for (const [width, height, mode] of [[390,844,'light'],[768,1024,'light'],[1440,1100,'dark']]) {
    await page.setViewportSize({width,height});
    await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    await navigate(page,'Processing');
    await page.evaluate(() => scrollTo(0,0));
    const scan = await accessibility(page);
    expect(scan.violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    expect(await page.locator('.path').evaluateAll(nodes => nodes.every(el => el.scrollWidth <= el.clientWidth + 1))).toBeTruthy();
    await navigate(page,'Library');
    await page.getByRole('button',{name:'A clearer picture.mkv'}).click();
    await page.evaluate(() => scrollTo(0,0));
    expect((await accessibility(page)).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    expect(await page.locator('.path').evaluateAll(nodes => nodes.every(el => el.scrollWidth <= el.clientWidth + 1))).toBeTruthy();
  }
  expect(errors).toEqual([]);
  expect(await page.evaluate(() => window.policyViolations)).toEqual([]);
  const noiseLabel=page.locator('label').filter({hasText:'Reduce noise'});
  await noiseLabel.click({position:{x:4,y:4}});
  await expect(page.getByRole('checkbox',{name:'Reduce noise',exact:true})).toBeChecked();
  await page.getByRole('checkbox',{name:'Reduce noise',exact:true}).uncheck();
  const shortControls = await page.evaluate(() => [...document.querySelectorAll('button,[role=combobox],input:not([type=hidden])')]
    .filter(el => el.getClientRects().length && !el.disabled && !el.closest('[aria-hidden=true]'))
    .map(el => ({control:el, target:el.closest('.astryx-selector,.astryx-text-input') || (el.type==='checkbox'?document.querySelector(`label[for="${el.id}"]`):null) || el}))
    .filter(({target}) => target.getBoundingClientRect().height < 44)
    .map(({control,target}) => ({name:control.getAttribute('aria-label') || control.textContent,height:target.getBoundingClientRect().height})));
  expect(shortControls).toEqual([]);
});

test('login error, keyboard focus, and one-use pairing UI', async ({page}) => {
  await page.goto('/');
  await page.getByLabel('Access key').fill('incorrect');
  await page.getByRole('button',{name:'Open Popcorn SR'}).click();
  await expect(page.getByRole('alert')).toHaveText('Access key is incorrect.');
  await page.getByLabel('Access key').fill('local-test-only-access-key-12345');
  await page.getByRole('button',{name:'Open Popcorn SR'}).click();
  await navigate(page,'Processing');
  await page.getByRole('button',{name:'Connect a worker',exact:true}).click();
  await expect(page.locator('#pair-code')).toContainText(/.{16,}/);
  await expect(page.getByText('This code expires in 10 minutes and can be used once.')).toBeVisible();
  await expect(page.getByRole('button',{name:'Copy pairing code'})).toBeVisible();
  expect((await accessibility(page)).violations).toEqual([]);
  await page.keyboard.press('Tab');
  expect(await page.evaluate(() => document.activeElement !== document.body)).toBeTruthy();
});

test('an explicit DLSS choice survives missing support without switching to resizing (UI fixture)', async ({page}) => {
  let available=true;
  await page.route('**/api/state',async route=>{
    const response=await route.fetch();
    if(!response.ok()){await route.fulfill({response});return;}
    const state=await response.json();
    state.workers.push({id:'engine-loss-fixture',name:'DLSS controls fixture',online:true,revoked:false,scratch:{path:'/scratch',free_bytes:1e9},capabilities:{
      initialization:'ready',engines:available?['resize','dlss-sr']:['resize'],encoders:['h264_nvidia'],platform:'Linux',architecture:'aarch64',notes:{},
      dlss_sr:available?{settings:[['performance','default']],temporal_qualities:['high']}:{},
    }});
    await route.fulfill({response,json:state});
  });
  await signIn(page);
  await page.getByRole('button',{name:'A clearer picture.mkv',exact:true}).click();
  const enhancement=page.getByRole('combobox',{name:'Enhancement',exact:true});
  // Automatically prefer verified DLSS when it is available; selecting it
  // explicitly then protects that intent when capabilities change.
  await expect(enhancement).toContainText('DLSS video upscaling');
  await enhancement.click();
  await page.getByRole('option',{name:'DLSS video upscaling · experimental',exact:true}).click();
  available=false;
  await expect(page.getByText('Selected enhancement is unavailable',{exact:true})).toBeVisible({timeout:6000});
  await expect(enhancement).toContainText('DLSS video upscaling');
  await expect(page.getByRole('button',{name:'Add to queue',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Preview 5 seconds',exact:true})).toBeDisabled();
  available=true;
  await expect(page.getByRole('button',{name:'Add to queue',exact:true})).toBeEnabled({timeout:6000});
  await expect(enhancement).toContainText('DLSS video upscaling');
});

test('large real frame comparison reviews a batch, invalidates edits, and continues saved full settings', async ({page}) => {
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await signIn(page);
  await expect.poll(()=>page.locator('#connection').textContent()).toMatch(/connected/i);
  await page.getByRole('button',{name:'A clearer picture.mkv',exact:true}).click();
  await page.getByRole('button',{name:'Another moment.mkv',exact:true}).click();
  const comparison=page.getByRole('region',{name:'Frame comparison',exact:true});
  await comparison.getByRole('combobox',{name:'Preview video',exact:true}).click();
  await page.getByRole('option',{name:'Another moment.mkv',exact:true}).click();
  const time=comparison.getByRole('spinbutton',{name:'Frame at',exact:true});
  await time.fill('2');await time.press('Tab');
  await expect(comparison.getByRole('img',{name:/Original frame/})).toBeVisible();
  await expect(comparison.getByRole('button',{name:'Run full batch',exact:true})).toBeDisabled();
  const [queued]=await Promise.all([
    page.waitForResponse(r=>r.url().endsWith('/api/jobs') && r.request().method()==='POST'),
    comparison.getByRole('button',{name:'Preview frame',exact:true}).click(),
  ]);
  expect(queued.ok()).toBeTruthy();
  const preview=await queued.json();
  expect(preview.path).toBe('Another moment.mkv');
  expect(preview.recipe).toMatchObject({preview_frame_time:2,preview_seconds:5,scale:2,codec:'h264'});
  const run=comparison.getByRole('button',{name:'Run full batch',exact:true});
  await expect(run).toBeEnabled({timeout:30000});
  const images=await comparison.locator('img').evaluateAll(imgs=>imgs.map(img=>({width:img.naturalWidth,height:img.naturalHeight,loaded:img.complete})));
  expect(images).toEqual([{width:320,height:180,loaded:true},{width:640,height:360,loaded:true}]);
  for(const [width,height,mode] of [[1440,1200,'light'],[768,1024,'dark'],[390,844,'dark']]) {
    await page.setViewportSize({width,height});await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    expect((await accessibility(page)).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    const boxes=await comparison.locator('.frame-image').evaluateAll(els=>els.map(el=>el.getBoundingClientRect().toJSON()));
    if(width>=768)expect(boxes[1].x).toBeGreaterThan(boxes[0].x+boxes[0].width);
    else expect(boxes[1].y).toBeGreaterThan(boxes[0].y+boxes[0].height);
    fs.mkdirSync('evidence/frame-comparison-20261013',{recursive:true});
    await page.evaluate(()=>{document.activeElement?.blur();scrollTo(0,0);});
    await page.screenshot({path:`evidence/frame-comparison-20261013/actual-cpu-${width}-${mode}.png`,fullPage:true,animations:'disabled'});
  }
  await page.setViewportSize({width:1440,height:1200});await page.emulateMedia({colorScheme:'light'});
  await comparison.getByRole('button',{name:'Expand preview',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>document.fullscreenElement?.getAttribute('aria-label'))).toBe('Frame comparison');
  await comparison.getByRole('button',{name:'Exit expanded preview',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>!!document.fullscreenElement)).toBe(false);
  await time.fill('3');await time.press('Tab');
  await expect(run).toBeDisabled();
  await expect(comparison.getByText('The frame or settings changed. Preview again to compare this selection.')).toBeVisible();
  await time.fill('2');await time.press('Tab');await expect(run).toBeEnabled();
  await page.getByRole('combobox',{name:'Output size',exact:true}).click();
  await page.getByRole('option',{name:'Three times the size (3×)',exact:true}).click();
  await expect(run).toBeDisabled();
  await page.locator(`[data-job-id="${preview.id}"]`).getByRole('button',{name:'Compare frame',exact:true}).click();
  await expect(run).toBeEnabled();
  await expect(page.getByRole('combobox',{name:'Output size',exact:true})).toContainText('Twice');
  const [continued,other]=await Promise.all([
    page.waitForResponse(r=>r.url().endsWith(`/${preview.id}/full`) && r.request().method()==='POST'),
    page.waitForResponse(r=>r.url().endsWith('/api/jobs') && r.request().method()==='POST'),
    run.click(),
  ]);
  expect(continued.ok()).toBeTruthy();expect(other.ok()).toBeTruthy();
  for(const response of [continued,other]) {
    const job=await response.json();
    expect(job.recipe).toMatchObject({preview_seconds:0,preview_frame_time:null,scale:2,codec:'h264'});
    const download=page.locator(`[data-job-id="${job.id}"]`).getByRole('link',{name:'Download copy',exact:true});
    await expect(download).toBeVisible({timeout:30000});
    const state=await (await page.request.get('/api/state')).json();
    expect(state.jobs.find(j=>j.id===job.id).result.audio_streams).toBe(1);
  }
  // A saved comparison also reopens after its source is no longer selected.
  await page.locator(`[data-job-id="${preview.id}"]`).getByRole('button',{name:'Compare frame',exact:true}).click();
  await expect(comparison.getByRole('button',{name:'Run full video',exact:true})).toBeEnabled();
  await expect(time).toHaveValue('2');
  expect(errors).toEqual([]);
});
