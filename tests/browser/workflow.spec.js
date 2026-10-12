import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs';
fs.mkdirSync('evidence/screenshots',{recursive:true});

async function signIn(page) {
  await page.goto('/');
  await page.getByLabel('Access key').fill('local-test-only-access-key-12345');
  await page.getByRole('button',{name:'Open Popcorn SR'}).click();
  await expect(page.getByRole('heading',{name:'A better home for your videos.'})).toBeVisible();
}

test('desktop preview completes on a real worker; responsive light/dark views pass accessibility', async ({page}) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await signIn(page);
  await expect.poll(async () => page.locator('#connection').textContent()).toContain('connected');
  await page.screenshot({path:'evidence/screenshots/overview-desktop.png',fullPage:true});
  await page.getByRole('navigation').getByRole('button',{name:'Library',exact:true}).click();
  await page.getByRole('button',{name:'A clearer picture.mkv'}).click();
  await page.getByLabel('Output size').selectOption('2');
  await page.getByLabel('Save copies to').fill('previews/check');
  await page.screenshot({path:'evidence/screenshots/library-desktop.png',fullPage:true});
  await page.getByRole('button',{name:'Preview 5 seconds'}).click();
  await expect(page.getByRole('heading',{name:'Your queue'})).toBeVisible();
  await expect(page.getByRole('link',{name:'Download preview'})).toBeVisible({timeout:30000});
  const download = await page.request.get(await page.getByRole('link',{name:'Download preview'}).getAttribute('href'));
  expect(download.ok()).toBeTruthy();
  expect((await download.body()).length).toBeGreaterThan(1000);
  await page.screenshot({path:'evidence/screenshots/queue-desktop.png',fullPage:true});
  for (const [width, height, mode] of [[390,844,'light'],[768,1024,'light'],[1440,1100,'dark']]) {
    await page.setViewportSize({width,height});
    await page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
    await page.getByRole('navigation').getByRole('button',{name:'Processing',exact:true}).click();
    await page.screenshot({path:`evidence/screenshots/processing-${width}-${mode}.png`,fullPage:true});
    const scan = await new AxeBuilder({page}).analyze();
    expect(scan.violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.getByRole('navigation').getByRole('button',{name:'Library',exact:true}).click();
    await page.getByRole('button',{name:'A clearer picture.mkv'}).click();
    await page.screenshot({path:`evidence/screenshots/library-${width}-${mode}.png`,fullPage:true});
    expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  }
  expect(errors).toEqual([]);
});

test('login error, keyboard focus, and one-use pairing UI', async ({page}) => {
  await page.goto('/');
  await page.getByLabel('Access key').fill('incorrect');
  await page.getByRole('button',{name:'Open Popcorn SR'}).click();
  await expect(page.getByRole('alert')).toHaveText('Access key is incorrect.');
  await page.getByLabel('Access key').fill('local-test-only-access-key-12345');
  await page.getByRole('button',{name:'Open Popcorn SR'}).click();
  await page.getByRole('navigation').getByRole('button',{name:'Processing',exact:true}).click();
  await page.getByRole('button',{name:'Connect a worker',exact:true}).click();
  await expect(page.locator('#pair-code')).toContainText(/.{16,}/);
  await expect(page.getByText('This code expires in 10 minutes and can be used once.')).toBeVisible();
  await expect(page.getByRole('button',{name:'Copy pairing code'})).toBeVisible();
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  await page.keyboard.press('Tab');
  expect(await page.evaluate(() => document.activeElement !== document.body)).toBeTruthy();
});
