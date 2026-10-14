import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs';
fs.mkdirSync('evidence/screenshots',{recursive:true});

test('read-only library picker navigates shows, preserves cross-library selections and previews a real source', async ({page}) => {
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await signIn(page);
  const input=page.getByRole('region',{name:'Input',exact:true});
  await input.getByRole('combobox',{name:'Library',exact:true}).click();
  await page.getByRole('option',{name:'TV shows',exact:true}).click();
  await input.getByLabel('Filter this folder',{exact:true}).fill('not present');
  await expect(input.getByText('No matches in this folder',{exact:true})).toBeVisible();
  await input.getByLabel('Filter this folder',{exact:true}).fill('COAST');
  await input.getByRole('button',{name:'The coastline',exact:true}).click();
  await input.getByRole('button',{name:'Season 01',exact:true}).click();
  await input.getByRole('button',{name:/The coastline S01E01\.mkv/}).click();
  await expect(input.getByText('1 selected',{exact:true})).toBeVisible();
  await input.getByRole('button',{name:'Up a folder',exact:true}).click();
  await expect(input.getByText('1 selected',{exact:true})).toBeVisible();
  await input.getByRole('combobox',{name:'Library',exact:true}).click();
  await page.getByRole('option',{name:'Movies',exact:true}).click();
  await input.getByRole('button',{name:'A quiet morning (2026)',exact:true}).click();
  await input.getByRole('button',{name:/A quiet morning\.mkv/}).click();
  await expect(input.getByText('2 selected',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Add 2 videos to queue',exact:true})).toBeEnabled();
  await input.getByRole('button',{name:'All folders',exact:true}).click();
  await input.getByRole('button',{name:'Clear selection',exact:true}).click();
  await input.getByRole('button',{name:'A quiet morning (2026)',exact:true}).click();
  await input.getByRole('button',{name:/A quiet morning\.mkv/}).click();
  await page.getByRole('button',{name:'Preview frame',exact:true}).click();
  await expect(page.locator('.frame-pair img')).toHaveCount(2,{timeout:30000});
  await expect.poll(()=>page.locator('.frame-pair img').evaluateAll(images=>images.every(image=>image.complete && image.naturalWidth))).toBeTruthy();
  const state=await (await page.request.get('/api/state')).json();
  const preview=state.jobs.find(job=>job.path==='@sources/movies/A quiet morning (2026)/A quiet morning.mkv' && job.status==='completed');
  expect(preview).toBeTruthy();
  fs.mkdirSync('evidence/library-20261013',{recursive:true});
  for(const [width,height,mode] of [[1440,1100,'light'],[820,1100,'dark'],[390,844,'dark']]) {
    await page.setViewportSize({width,height});await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    expect((await accessibility(page)).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    await page.evaluate(()=>{document.activeElement?.blur();scrollTo(0,0);});
    if(width===1440) await page.locator('.io-grid').screenshot({path:'evidence/library-20261013/picker-panels.png',animations:'disabled'});
    await page.screenshot({path:`evidence/library-20261013/picker-${width}-${mode}.png`,fullPage:true,animations:'disabled'});
  }
  await page.getByRole('button',{name:'Run full video',exact:true}).click();
  await expect.poll(async()=>{
    const jobs=(await (await page.request.get('/api/state')).json()).jobs;
    return jobs.some(job=>job.path===preview.path && !job.recipe.preview_seconds && job.status==='completed');
  },{timeout:30000}).toBeTruthy();
  expect(errors).toEqual([]);
});

test('worker updates have a simple idle-safe action and recovery state (UI fixture; no container replacement)', async ({page}) => {
  let pending=false, phase='current', draining=false, enabled=true, requested=false;
  await page.route('**/api/state',async route=>{
    const response=await route.fetch();
    if(!response.ok()) {await route.fulfill({response});return;}
    const state=await response.json();
    state.workers.push({id:'updates-ui-fixture',name:'Update controls fixture',online:true,revoked:false,update_pending:pending,scratch:{path:'/external/popcorn-scratch',free_bytes:1e9},capabilities:{initialization:'ready',engines:['resize'],encoders:['h264_cpu'],platform:'UI fixture · no container replacement',architecture:'local',updates:{version:'0.4.0',enabled,automatic:true,state:phase,draining}}});
    await route.fulfill({response,json:state});
  });
  await page.route('**/api/workers/updates-ui-fixture/update',async route=>{
    expect(route.request().method()).toBe('POST');requested=true;pending=true;
    await route.fulfill({json:{request_id:'ui-fixture'}});
  });
  await signIn(page);await navigate(page,'Processing');
  const device=page.getByRole('article',{name:'Update controls fixture'});
  await expect(device.getByText('Worker 0.4.0',{exact:true})).toBeVisible();
  await device.getByRole('button',{name:'Check for updates',exact:true}).click();
  expect(requested).toBeTruthy();
  await expect(device.getByRole('button',{name:'Check for updates',exact:true})).toBeDisabled();
  pending=false;phase='waiting';draining=true;
  await expect(device.getByText('Updating',{exact:true})).toBeVisible({timeout:6000});
  await expect(device.getByRole('status',{name:'Worker update'})).toContainText('current job finishes');
  phase='rolled_back';draining=false;
  await expect(device.getByRole('status',{name:'Worker update'})).toContainText('previous version was restored',{timeout:6000});
  await expect(device.getByRole('button',{name:'Check for updates',exact:true})).toBeEnabled();
  fs.mkdirSync('evidence/worker-updates-20261013',{recursive:true});
  for(const [width,height,mode] of [[1440,1000,'light'],[390,844,'dark']]) {
    await page.setViewportSize({width,height});await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    expect((await accessibility(page)).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    await page.screenshot({path:`evidence/worker-updates-20261013/controls-${width}-${mode}.png`,fullPage:true,animations:'disabled'});
  }
  enabled=false;
  await expect(device.getByRole('button',{name:'Check for updates',exact:true})).toBeDisabled({timeout:6000});
});

test.afterEach(async ({page}) => {
  // Polling can still be inside route.fetch/json when assertions finish.
  // Drain those handlers before Playwright disposes the request context.
  await page.unrouteAll({behavior:'wait'});
});

test('resolution rules preserve mixed-batch intent, previews and original/final row dimensions', async ({page}) => {
  await signIn(page);
  const input=page.getByRole('region',{name:'Input',exact:true});
  await expect(input.getByText('320 × 180',{exact:true})).toHaveCount(2);
  await input.getByRole('button',{name:'Select page',exact:true}).click();
  await expect(page.getByRole('button',{name:'Add 2 videos to queue',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'Resolution rules',exact:true}).click();
  await page.getByRole('checkbox',{name:'Set output by input resolution',exact:true}).check();
  await expect(page.getByRole('combobox',{name:'720p output',exact:true})).toContainText('1080p');
  await expect(page.getByRole('combobox',{name:'1080p output',exact:true})).toContainText('4K');
  await expect(page.getByRole('combobox',{name:'4K output',exact:true})).toContainText('Keep resolution');
  // Tiny generated inputs use Keep resolution here; the backend/media tests
  // exercise true target fitting. This is a real CPU preview and batch run.
  await page.getByRole('combobox',{name:'480p output',exact:true}).click();
  await expect(page.getByRole('option',{name:'480p',exact:true})).toHaveCount(0);
  await page.getByRole('option',{name:'Keep resolution',exact:true}).click();
  await page.getByRole('button',{name:'Preview frame',exact:true}).click();
  await expect(page.locator('.frame-pair img')).toHaveCount(2,{timeout:30000});
  await expect.poll(()=>page.locator('.frame-pair img').evaluateAll(images=>images.every(image=>image.complete && image.naturalWidth))).toBeTruthy();
  const preview=(await (await page.request.get('/api/state')).json()).jobs.find(job=>job.recipe.resolution_rules);
  expect(preview.recipe).toMatchObject({scale:1,resolution_rules:{'480':'keep','720':'1080','1080':'2160'}});
  const output=page.getByRole('region',{name:'Output queue',exact:true});
  await expect(output.locator(`[data-job-id="${preview.id}"] .media-spec`)).toContainText('320 × 180');
  await expect(output.locator(`[data-job-id="${preview.id}"] .media-spec`)).toContainText('H.264');
  await navigate(page,'Processing');await page.getByRole('button',{name:'Back to videos',exact:true}).click();
  await expect(page.getByRole('combobox',{name:'480p output',exact:true})).toContainText('Keep resolution');
  await page.getByRole('button',{name:'Run full batch',exact:true}).click();
  await expect.poll(async()=>{
    const state=await (await page.request.get('/api/state')).json();
    return state.jobs.filter(job=>job.recipe.resolution_rules && !job.recipe.preview_seconds && job.status==='completed').length;
  },{timeout:30000}).toBe(2);
  const full=(await (await page.request.get('/api/state')).json()).jobs.filter(job=>job.recipe.resolution_rules && !job.recipe.preview_seconds);
  expect(full).toHaveLength(2);
  expect(full.every(job=>job.recipe.scale===1 && job.recipe.resolution_rules['720']==='1080')).toBeTruthy();
  for(const job of full)await expect(output.locator(`[data-job-id="${job.id}"]`).getByRole('link',{name:'Download copy',exact:true})).toBeVisible({timeout:10000});
  for(const [width,height,mode] of [[1440,1100,'light'],[768,1024,'dark'],[390,844,'dark']]) {
    await page.setViewportSize({width,height});await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    expect((await accessibility(page)).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    await page.locator('main').focus();await page.evaluate(()=>scrollTo(0,0));
    await page.screenshot({path:`evidence/final-install-20261013/refined-cpu-${width}-${mode}.png`,fullPage:true,animations:'disabled'});
  }
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
  await expect(page.locator('#connection')).toHaveClass(/connection-chip/);
  await expect(page.locator('#connection')).toHaveAttribute('data-variant','success');
  const alignment=await page.evaluate(()=>{
    const chip=document.querySelector('#connection').getBoundingClientRect();
    const button=document.querySelector('.header-actions button').getBoundingClientRect();
    return Math.abs(chip.y+chip.height/2-button.y-button.height/2);
  });
  expect(alignment).toBeLessThan(1);
  await expect(page.getByRole('navigation')).toHaveCount(1);
  await expect(page.getByRole('navigation',{name:'Library folders',exact:true})).toHaveCount(1);
  await expect(page.getByRole('region',{name:'Upscaling settings',exact:true}).getByRole('combobox')).toHaveCount(3);
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
  await expect(page.getByRole('region',{name:'Upscaling settings',exact:true}).getByRole('combobox')).toHaveCount(3);
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

async function completeSignIn(page) {
  const skip=page.getByRole('button',{name:'Not now',exact:true});
  const videos=page.getByRole('heading',{name:'Videos',exact:true});
  await expect(skip.or(videos)).toBeVisible();
  if(await skip.isVisible())await skip.click();
  await expect(videos).toBeVisible();
}

async function signIn(page) {
  await page.goto('/');
  await page.getByLabel(/^Username/).fill('admin');
  await page.getByLabel(/^Password/).fill('local-test-only-password-12345');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await completeSignIn(page);
  await expect(page.getByRole('heading',{name:'Videos',exact:true})).toBeVisible();
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
  const [previewResponse]=await Promise.all([
    page.waitForResponse(response=>response.url().endsWith('/api/jobs') && response.request().method()==='POST'),
    page.getByRole('button',{name:'Preview 5 seconds'}).click(),
  ]);
  const preview=await previewResponse.json(), previewRow=page.locator(`[data-job-id="${preview.id}"]`);
  await expect(page.getByRole('heading',{name:'Output queue',exact:true})).toBeVisible();
  await expect(previewRow.getByRole('link',{name:'Download preview'})).toBeVisible({timeout:30000});
  const download = await page.request.get(await previewRow.getByRole('link',{name:'Download preview'}).getAttribute('href'));
  expect(download.ok()).toBeTruthy();
  expect((await download.body()).length).toBeGreaterThan(1000);
  await page.evaluate(() => scrollTo(0,0));
  const [continued] = await Promise.all([
    page.waitForResponse(r => r.url().endsWith('/full') && r.request().method() === 'POST'),
    previewRow.getByRole('button',{name:'Enhance full video'}).click()
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
  await page.getByLabel(/^Username/).fill('admin');
  await page.getByLabel(/^Password/).fill('incorrect');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.getByRole('alert')).toHaveText('Username or password is incorrect.');
  await page.getByLabel(/^Username/).fill('admin');
  await page.getByLabel(/^Password/).fill('local-test-only-password-12345');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await completeSignIn(page);
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

test('linked comparison zoom inspects matching detail, pans either side, resets and keeps expanded views', async ({page}) => {
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error' && /content security|violates|refused/i.test(message.text()))errors.push(message.text());});
  await signIn(page);
  await page.getByRole('button',{name:'A clearer picture.mkv',exact:true}).click();
  const comparison=page.getByRole('region',{name:'Frame comparison',exact:true});
  await comparison.getByRole('button',{name:'Preview frame',exact:true}).click();
  await expect(comparison.getByRole('button',{name:'Run full video',exact:true})).toBeEnabled({timeout:30000});
  const viewports=comparison.locator('.frame-image');
  const readView=()=>viewports.evaluateAll(panes=>panes.map(pane=>{
    const image=pane.querySelector('img'), matrix=new DOMMatrix(getComputedStyle(image).transform);
    const fit=Math.min(pane.clientWidth/image.naturalWidth,pane.clientHeight/image.naturalHeight);
    return {zoom:matrix.a,x:.5-matrix.e/(image.naturalWidth*fit*matrix.a),y:.5-matrix.f/(image.naturalHeight*fit*matrix.a)};
  }));
  const matched=async()=>{
    const views=await readView();expect(views[0].zoom).toBeCloseTo(views[1].zoom,4);
    expect(views[0].x).toBeCloseTo(views[1].x,4);expect(views[0].y).toBeCloseTo(views[1].y,4);
    expect(views.every(view=>[view.zoom,view.x,view.y].every(Number.isFinite))).toBeTruthy();return views[0];
  };
  await expect(comparison.getByRole('button',{name:'Zoom out',exact:true})).toBeDisabled();
  await comparison.getByRole('button',{name:'Zoom in',exact:true}).click();
  await comparison.getByRole('button',{name:'Zoom in',exact:true}).click();
  await expect.poll(async()=>(await readView())[0].zoom).toBe(4);
  for(const index of [0,1]) {
    await viewports.nth(index).scrollIntoViewIfNeeded();
    const box=await viewports.nth(index).boundingBox(), before=await matched();
    await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
    await page.mouse.move(box.x+box.width/2+50,box.y+box.height/2-25,{steps:5});await page.mouse.up();
    await expect.poll(async()=>(await readView())[0].x).toBeLessThan(before.x-.01);
    expect((await matched()).y).toBeGreaterThan(before.y);
  }
  // A wheel zoom stays anchored on the pointed picture detail on both sides.
  const box=await viewports.nth(1).boundingBox(), before=await matched();
  await viewports.nth(1).evaluate(pane=>pane.addEventListener('wheel',event=>{
    const rect=pane.getBoundingClientRect(), image=pane.querySelector('img');
    const fit=Math.min(pane.clientWidth/image.naturalWidth,pane.clientHeight/image.naturalHeight);
    window.zoomAnchor={x:(event.clientX-rect.left-pane.clientWidth/2)/(image.naturalWidth*fit),y:(event.clientY-rect.top-pane.clientHeight/2)/(image.naturalHeight*fit)};
  },{once:true}));
  await page.mouse.move(box.x+box.width*.65,box.y+box.height*.4);
  await page.mouse.wheel(0,-100);
  await expect.poll(async()=>(await readView())[0].zoom).toBeGreaterThan(4);
  const after=await matched(), anchor=await page.evaluate(()=>window.zoomAnchor);
  expect(after.x+anchor.x/after.zoom).toBeCloseTo(before.x+anchor.x/before.zoom,4);
  expect(after.y+anchor.y/after.zoom).toBeCloseTo(before.y+anchor.y/before.zoom,4);
  await viewports.nth(1).focus();await page.keyboard.press('ArrowRight');
  await expect.poll(async()=>(await readView())[0].x).toBeGreaterThan(after.x);
  await page.keyboard.press('=');await expect.poll(async()=>(await readView())[0].zoom).toBe(8);
  await expect(comparison.getByRole('button',{name:'Zoom in',exact:true})).toBeDisabled();
  await page.waitForResponse(response=>response.url().endsWith('/api/state') && response.ok());
  expect((await matched()).zoom).toBe(8);
  // Resize and the manager's recurring state refresh must keep the inspected detail.
  fs.mkdirSync('evidence/linked-zoom-20261014',{recursive:true});
  for(const [width,height,mode] of [[1440,1100,'light'],[820,1100,'dark'],[390,844,'dark']]) {
    await page.setViewportSize({width,height});await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    await matched();await expect.poll(async()=>(await readView())[0].zoom).toBe(8);
    expect((await accessibility(page)).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    if(width===390) {
      await viewports.nth(1).scrollIntoViewIfNeeded();
      const mobile=await viewports.nth(1).boundingBox(), initial=await matched();
      const touch=await page.context().newCDPSession(page);
      await touch.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:mobile.x+mobile.width/2,y:mobile.y+mobile.height/2}]});
      await touch.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:mobile.x+mobile.width/2+35,y:mobile.y+mobile.height/2}]});
      await touch.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await touch.detach();
      await expect.poll(async()=>(await readView())[0].x).toBeLessThan(initial.x);await matched();
    }
    await page.evaluate(()=>document.activeElement?.blur());
    await page.waitForTimeout(100);
    await comparison.screenshot({path:`evidence/linked-zoom-20261014/zoom-${width}-${mode}.png`,animations:'disabled'});
  }
  await page.setViewportSize({width:1440,height:1100});await page.emulateMedia({colorScheme:'light'});
  await comparison.getByRole('button',{name:'Expand preview',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>document.fullscreenElement?.getAttribute('aria-label'))).toBe('Frame comparison');
  await matched();expect((await readView())[0].zoom).toBe(8);
  await comparison.getByRole('button',{name:'Exit expanded preview',exact:true}).click();
  await comparison.getByRole('button',{name:'Fit',exact:true}).click();
  await expect.poll(async()=>(await readView())[0]).toEqual({zoom:1,x:.5,y:.5});await matched();
  const resetBox=await viewports.nth(0).boundingBox();
  await viewports.nth(0).dblclick({position:{x:resetBox.width*.6,y:resetBox.height*.4}});
  await expect.poll(async()=>(await readView())[0].zoom).toBe(2);await matched();
  await viewports.nth(0).focus();await page.keyboard.press('0');
  await expect.poll(async()=>(await readView())[0].zoom).toBe(1);
  await comparison.getByRole('button',{name:'Zoom in',exact:true}).click();
  const time=comparison.getByRole('spinbutton',{name:'Frame at',exact:true});await time.fill('1');await time.press('Tab');
  await expect(comparison.getByLabel('Comparison magnification',{exact:true})).toHaveText('1×');
  await expect(comparison.getByRole('button',{name:'Run full video',exact:true})).toBeDisabled();
  expect(errors).toEqual([]);
});

test('delete preview clears either view while the original and full copy remain usable', async ({page}) => {
  await signIn(page);
  await page.getByRole('button',{name:'A clearer picture.mkv',exact:true}).click();
  const comparison=page.getByRole('region',{name:'Frame comparison',exact:true});
  const [response]=await Promise.all([
    page.waitForResponse(response=>response.url().endsWith('/api/jobs') && response.request().method()==='POST'),
    comparison.getByRole('button',{name:'Preview frame',exact:true}).click(),
  ]);
  const preview=await response.json();
  await expect(comparison.getByRole('button',{name:'Run full video',exact:true})).toBeEnabled({timeout:30000});
  const original=await (await page.request.get('/api/library/frame?path=A%20clearer%20picture.mkv&seconds=0')).body();
  const [continued]=await Promise.all([
    page.waitForResponse(response=>response.url().endsWith(`/${preview.id}/full`) && response.request().method()==='POST'),
    comparison.getByRole('button',{name:'Run full video',exact:true}).click(),
  ]);
  const full=await continued.json(), fullRow=page.locator(`[data-job-id="${full.id}"]`);
  await expect(fullRow.getByRole('link',{name:'Download copy',exact:true})).toBeVisible({timeout:30000});
  await expect(fullRow.getByRole('button',{name:'Delete preview',exact:true})).toHaveCount(0);
  const copy=await (await page.request.get(`/api/jobs/${full.id}/download`)).body();
  const previewRow=page.locator(`[data-job-id="${preview.id}"]`);
  await previewRow.getByRole('button',{name:'Compare frame',exact:true}).click();
  await expect(comparison.getByRole('button',{name:'Run full video',exact:true})).toBeEnabled();
  await comparison.getByRole('button',{name:'Delete preview',exact:true}).click();
  await expect(previewRow).toHaveCount(0);
  await expect(comparison.getByRole('img',{name:/Enhanced frame/})).toHaveCount(0);
  await expect(comparison.getByRole('button',{name:'Run full video',exact:true})).toBeDisabled();
  expect((await page.request.get(`/api/jobs/${preview.id}/download`)).status()).toBe(404);
  expect(await (await page.request.get(`/api/jobs/${full.id}/download`)).body()).toEqual(copy);
  expect(await (await page.request.get('/api/library/frame?path=A%20clearer%20picture.mkv&seconds=0')).body()).toEqual(original);
  const [next]=await Promise.all([
    page.waitForResponse(response=>response.url().endsWith('/api/jobs') && response.request().method()==='POST'),
    comparison.getByRole('button',{name:'Preview frame',exact:true}).click(),
  ]);
  const second=await next.json(), secondRow=page.locator(`[data-job-id="${second.id}"]`);
  await expect(secondRow.getByRole('button',{name:'Delete preview',exact:true})).toBeVisible({timeout:30000});
  await secondRow.getByRole('button',{name:'Delete preview',exact:true}).click();
  await expect(secondRow).toHaveCount(0);
  await expect(comparison.getByRole('img',{name:/Enhanced frame/})).toHaveCount(0);
  await expect(fullRow.getByRole('link',{name:'Download copy',exact:true})).toBeVisible();
});

test('large real frame comparison reviews a batch, invalidates edits, and continues saved full settings', async ({page}) => {
  let changeAvailableCodec=false;
  // Only capability changes are simulated; preview and full jobs use the real CPU worker.
  await page.route('**/api/state',async route=>{
    const response=await route.fetch();
    if(!response.ok()){await route.fulfill({response});return;}
    const state=await response.json();
    if(changeAvailableCodec)for(const worker of state.workers)worker.capabilities.encoders=['hevc_cpu'];
    await route.fulfill({response,json:state});
  });
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
  changeAvailableCodec=true;
  await expect(page.getByRole('combobox',{name:'Video format',exact:true})).toContainText('H.265 / HEVC');
  await expect(run).toBeDisabled();
  await expect(comparison.getByText('The frame or settings changed. Preview again to compare this selection.')).toBeVisible();
  changeAvailableCodec=false;
  await expect(page.getByRole('combobox',{name:'Video format',exact:true})).toContainText('H.264');
  await expect(run).toBeEnabled();
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
