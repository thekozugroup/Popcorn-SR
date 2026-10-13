import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs';
fs.mkdirSync('evidence/screenshots',{recursive:true});

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
  await page.getByRole('button',{name:'More options',exact:true}).click();
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
    await page.screenshot({path:`evidence/screenshots/dlss-controls-${width}-${mode}.png`,fullPage:true,animations:'disabled'});
    expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  }
  await navigate(page,'Queue');
  await expect(page.locator('#jobs')).toContainText('H.265 / HEVC');
  await expect(page.locator('#jobs')).toContainText('Preset: K · Motion estimation: Fast');
  for (const [width,height,mode] of [[1440,1100,'light'],[390,844,'dark']]) {
    await page.setViewportSize({width,height});
    await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    await page.evaluate(()=>scrollTo(0,0));
    await page.screenshot({path:`evidence/screenshots/dlss-summary-${width}-${mode}.png`,fullPage:true,animations:'disabled'});
    expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  }
});

async function navigate(page, name) {
  const toggle = page.getByTestId('mobile-nav-toggle');
  // Astryx's inherited md breakpoint is 768px. Viewport updates resolve
  // before its React media-query render; wait for the intended nav surface.
  const mobile = page.viewportSize().width < 768;
  if (mobile) {
    await expect(toggle).toBeVisible();
    await toggle.click();
    await page.getByRole('dialog',{name:'Navigation',exact:true}).getByRole('button',{name,exact:true}).click();
    await expect(page.getByRole('dialog',{name:'Navigation',exact:true})).not.toBeVisible();
  } else {
    await expect(toggle).not.toBeVisible();
    await page.getByRole('navigation').getByRole('button', {name, exact:true}).click();
  }
}

async function signIn(page) {
  await page.goto('/');
  await page.getByLabel('Access key').fill('local-test-only-access-key-12345');
  await page.getByRole('button',{name:'Open Popcorn SR'}).click();
  await expect(page.getByRole('heading',{name:'A better home for your videos.'})).toBeVisible();
}

test('desktop preview completes on a real worker; responsive light/dark views pass accessibility', async ({page}) => {
  const errors = [];
  await page.addInitScript(() => {
    window.policyViolations = [];
    document.addEventListener('securitypolicyviolation', event => window.policyViolations.push(event.violatedDirective));
  });
  page.on('pageerror', error => errors.push(error.message));
  await signIn(page);
  await expect.poll(async () => page.locator('#connection').textContent()).toContain('connected');
  await page.evaluate(() => scrollTo(0,0));
  await page.screenshot({path:'evidence/screenshots/overview-desktop.png',fullPage:true,animations:"disabled"});
  await page.getByRole('button',{name:'Try a preview'}).click();
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
  await page.screenshot({path:'evidence/screenshots/library-desktop.png',fullPage:true,animations:"disabled"});
  await page.getByRole('button',{name:'Preview 5 seconds'}).click();
  await expect(page.getByRole('heading',{name:'Your queue'})).toBeVisible();
  await expect(page.getByRole('link',{name:'Download preview'})).toBeVisible({timeout:30000});
  const download = await page.request.get(await page.getByRole('link',{name:'Download preview'}).getAttribute('href'));
  expect(download.ok()).toBeTruthy();
  expect((await download.body()).length).toBeGreaterThan(1000);
  await page.evaluate(() => scrollTo(0,0));
  await page.screenshot({path:'evidence/screenshots/queue-desktop.png',fullPage:true,animations:"disabled"});
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
  const completed = page.locator('#jobs').getByRole('link',{name:'Download copy',exact:true});
  await expect(completed).toBeVisible({timeout:30000});
  const finished = (await (await page.request.get('/api/state')).json()).jobs.find(j => j.id === full.id);
  expect(finished.status).toBe('completed');
  expect(finished.result.duration).toBeGreaterThan(5.5);
  expect(finished.result.audio_streams).toBe(1);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  for (const [width, height, mode] of [[390,844,'light'],[768,1024,'light'],[1440,1100,'dark']]) {
    await page.setViewportSize({width,height});
    await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    await navigate(page,'Processing');
    await page.evaluate(() => scrollTo(0,0));
  await page.screenshot({path:`evidence/screenshots/processing-${width}-${mode}.png`,fullPage:true,animations:"disabled"});
    const scan = await new AxeBuilder({page}).analyze();
    expect(scan.violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    expect(await page.locator('.path').evaluateAll(nodes => nodes.every(el => el.scrollWidth <= el.clientWidth + 1))).toBeTruthy();
    await navigate(page,'Library');
    await page.getByRole('button',{name:'A clearer picture.mkv'}).click();
    await page.evaluate(() => scrollTo(0,0));
  await page.screenshot({path:`evidence/screenshots/library-${width}-${mode}.png`,fullPage:true,animations:"disabled"});
    expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    expect(await page.locator('.path').evaluateAll(nodes => nodes.every(el => el.scrollWidth <= el.clientWidth + 1))).toBeTruthy();
  }
  expect(errors).toEqual([]);
  expect(await page.evaluate(() => window.policyViolations)).toEqual([]);
  const shortControls = await page.evaluate(() => [...document.querySelectorAll('button,[role=combobox],input:not([type=hidden])')]
    .filter(el => el.getClientRects().length && !el.disabled && !el.closest('[aria-hidden=true]'))
    .map(el => ({control:el, target:el.closest('.astryx-selector,.astryx-text-input') || el}))
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
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  await page.keyboard.press('Tab');
  expect(await page.evaluate(() => document.activeElement !== document.body)).toBeTruthy();
});
