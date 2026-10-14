import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs';

// Chromium's disposable authenticator generates real credentials/signatures.
// This checks WebAuthn end-to-end; it does not enroll a physical user device.
test('fresh installation changes admin password, then registers and signs in with a verified passkey', async ({page,context}) => {
  const directory='evidence/login-20261013';
  fs.mkdirSync(directory,{recursive:true});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const cdp=await context.newCDPSession(page);
  await cdp.send('WebAuthn.enable');
  const {authenticatorId}=await cdp.send('WebAuthn.addVirtualAuthenticator',{options:{
    protocol:'ctap2',transport:'internal',hasResidentKey:true,hasUserVerification:true,
    isUserVerified:true,automaticPresenceSimulation:true,
  }});
  const audit=async()=>{
    expect((await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()).violations).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  };
  try {
    await page.goto('http://localhost:18878/');
    await expect(page.getByRole('heading',{name:'Welcome to Popcorn SR'})).toBeVisible();
    await expect(page.getByText('First sign-in: admin / admin. You’ll choose a new password next.')).toBeVisible();
    for(const [width,height,scheme] of [[1440,1000,'light'],[390,844,'dark']]){
      await page.setViewportSize({width,height});await page.emulateMedia({colorScheme:scheme,reducedMotion:'reduce'});
      await audit();await page.screenshot({path:`${directory}/sign-in-${width}.png`,fullPage:true,animations:'disabled'});
    }
    await page.getByLabel(/^Username/).fill('admin');
    await page.getByLabel(/^Password/).fill('admin');
    await page.getByRole('button',{name:'Sign in',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Make it yours'})).toBeVisible();
    expect((await page.request.get('http://localhost:18878/api/state')).status()).toBe(403);
    await page.getByLabel(/^Username/).fill('test-owner');
    await page.getByLabel(/^New password/).fill('browser-test-password');
    await page.getByLabel(/^Confirm password/).fill('does-not-match');
    await page.getByRole('button',{name:'Save password',exact:true}).click();
    await expect(page.getByRole('alert')).toHaveText('The passwords do not match. Enter them again.');
    await page.getByLabel(/^Confirm password/).fill('browser-test-password');
    await audit();await page.screenshot({path:`${directory}/change-password-phone.png`,fullPage:true,animations:'disabled'});
    await page.getByRole('button',{name:'Save password',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Add a passkey'})).toBeVisible();
    await audit();await page.screenshot({path:`${directory}/passkey-phone.png`,fullPage:true,animations:'disabled'});
    await page.setViewportSize({width:1440,height:1000});await page.emulateMedia({colorScheme:'light'});
    await audit();await page.screenshot({path:`${directory}/passkey-desktop.png`,fullPage:true,animations:'disabled'});
    await page.getByRole('button',{name:'Create a passkey',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Videos',exact:true})).toBeVisible();
    const account=await (await page.request.get('http://localhost:18878/api/auth/session')).json();
    expect(account.username).toBe('test-owner');expect(account.passkeys).toBe(1);
    await page.request.post('http://localhost:18878/api/logout');await page.reload();
    await page.getByLabel(/^Username/).fill('admin');
    await page.getByLabel(/^Password/).fill('admin');
    await page.getByRole('button',{name:'Sign in',exact:true}).click();
    await expect(page.getByRole('alert')).toHaveText('Username or password is incorrect.');
    // Invalid origin and altered signature must fail against genuine assertions.
    for(const mutation of ['origin','signature']){
      await page.route('**/api/auth/passkeys/login/verify',async route=>{
        const payload=route.request().postDataJSON();
        const response=payload.credential.response;
        if(mutation==='origin'){
          const data=JSON.parse(Buffer.from(response.clientDataJSON,'base64url').toString());
          data.origin='https://wrong.example';response.clientDataJSON=Buffer.from(JSON.stringify(data)).toString('base64url');
        }else{
          const bytes=Buffer.from(response.signature,'base64url');bytes[bytes.length-1]^=1;response.signature=bytes.toString('base64url');
        }
        const result=await route.fetch({postData:JSON.stringify(payload)});
        expect(result.status()).toBe(401);await route.fulfill({response:result});
      });
      await page.getByRole('button',{name:'Sign in with a passkey',exact:true}).click();
      await expect(page.getByRole('alert')).toContainText('Passkey could not be verified.');
      await page.unrouteAll({behavior:'wait'});
    }
    let signed;
    page.on('request',request=>{if(request.url().endsWith('/api/auth/passkeys/login/verify'))signed=request.postDataJSON();});
    await page.getByRole('button',{name:'Sign in with a passkey',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Videos',exact:true})).toBeVisible();
    expect((await page.request.post('http://localhost:18878/api/auth/passkeys/login/verify',{data:signed})).status()).toBe(400);
    expect(await (await page.request.get('http://localhost:18878/api/auth/session')).json()).toMatchObject({username:'test-owner',passkeys:1});
    await page.getByRole('button',{name:'Devices & storage',exact:true}).click();
    await page.getByRole('button',{name:'Storage & help',exact:true}).click();
    await page.getByRole('button',{name:'Add a passkey',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Add a passkey',exact:true})).toBeVisible();
    // Manual enrollment stays open across the former 3-second workspace poll.
    await page.waitForTimeout(3200);
    await expect(page.getByRole('heading',{name:'Add a passkey',exact:true})).toBeVisible();
    await page.getByRole('button',{name:'Not now',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Your processing power',exact:true})).toBeVisible();
    await page.getByRole('button',{name:'Back to videos',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Videos',exact:true})).toBeVisible();
    expect(errors).toEqual([]);
    fs.writeFileSync(`${directory}/browser-auth-receipt.json`,JSON.stringify({
      default_password_changed:true,management_blocked_before_change:true,passkey_registration:true,
      cryptographic_passkey_login:true,altered_origin_rejected:true,altered_signature_rejected:true,replay_rejected:true,
      accessibility_and_overflow:true,physical_user_passkey:false,
    },null,2));
  }finally{await cdp.send('WebAuthn.removeVirtualAuthenticator',{authenticatorId}).catch(()=>{});}
});
