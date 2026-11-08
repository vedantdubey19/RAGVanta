import {test,before,after} from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {fixture,pause} from './browser_support.mjs';
let app;
before(async()=>{app=await fixture('rag',fileURLToPath(new URL('..',import.meta.url)));});
after(async()=>{if(app)await app.close();});
async function login(page,user,password=app.password){
 await page.locator('#username').fill(user);await page.locator('#password').fill(password);
 await page.getByRole('button',{name:'Sign in',exact:true}).click();
}
test('expired account content and delayed responses cannot survive a different login or another-tab logout',async()=>{
 const page=await app.context.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.goto(app.origin);await login(page,'qa_alpha');await page.locator('#workspace').waitFor({state:'visible'});
 await page.locator('[data-view=chat]').click();await page.locator('#question').fill('What is the alpha project codename?');await page.getByRole('button',{name:'Retrieve and answer'}).click();
 await page.locator('#answer').filter({hasText:'Violet Orchard'}).waitFor();
 let ready,release;const backendReady=new Promise(resolve=>ready=resolve),gate=new Promise(resolve=>release=resolve);
 await page.route('**/v1/chat',async route=>{const response=await route.fetch();ready();await gate;try{await route.fulfill({response});}catch{/* The account reset is expected to cancel this request. */}});
 await page.getByRole('button',{name:'Retrieve and answer'}).click();await backendReady;app.expire('qa_alpha');
 await page.locator('[data-view=reports]').click();await page.locator('#login').waitFor({state:'visible'});
 assert.equal(await page.locator('#answer').innerText(),'');assert.equal(await page.locator('#identity').innerText(),'');
 await login(page,'qa_beta','an-intentionally-incorrect-password');
 await page.locator('#status').filter({hasText:'401'}).waitFor();assert.equal(await page.getByRole('button',{name:'Sign in',exact:true}).isEnabled(),true);
 await login(page,'qa_beta');await page.locator('#identity').filter({hasText:'qa_beta'}).waitFor();release();await pause(250);
 await page.locator('[data-view=chat]').click();
 for(const id of ['answer','citations','trace','report','experiment-result'])assert.equal(await page.locator('#'+id).innerText(),'');
 assert.equal(await page.locator('#question').inputValue(),'');assert.equal(await page.locator('#collection-select option').count(),0);
 assert.equal((await app.api('/v1/documents?collection_id='+app.metadata.alpha_collection)).status(),404);
 const other=await app.context.newPage();await other.goto(app.origin);await other.locator('#workspace').waitFor({state:'visible'});
 await page.locator('#logout').click();await other.locator('#login').waitFor({state:'visible'});assert.equal(await other.locator('#identity').innerText(),'');
 assert.deepEqual(errors,[]);await other.close();await page.close();
});
test('the browser deletes a collection and recovers from the default ten-collection quota',async()=>{
 const page=await app.context.newPage();await page.goto(app.origin);await login(page,'qa_beta');await page.locator('#workspace').waitFor({state:'visible'});
 for(let i=0;i<10;i++)assert.equal((await app.api('/v1/collections','POST',{name:'Quota '+i})).status(),201);
 assert.equal((await app.api('/v1/collections','POST',{name:'Over quota'})).status(),413);
 await page.reload();await page.locator('#collection-select option').nth(9).waitFor({state:'attached'});
 page.once('dialog',dialog=>dialog.accept());await page.locator('#delete-collection').click();await page.locator('#status').filter({hasText:'Collection deleted.'}).waitFor();
 assert.equal(await page.locator('#collection-select option').count(),9);
 await page.locator('#collection-name').fill('Recovered capacity');await page.getByRole('button',{name:'Create collection',exact:true}).click();
 await page.locator('#status').filter({hasText:'Collection created.'}).waitFor();assert.equal(await page.locator('#collection-select option').count(),10);
 assert.equal(await page.locator('#collection-select option:checked').innerText(),'Recovered capacity');
 await page.locator('#logout').click();await page.close();
});
test('new controls fit narrow screens and collections remain usable',async()=>{
 const page=await app.context.newPage();await page.goto(app.origin);await login(page,'qa_alpha');await page.locator('#workspace').waitFor({state:'visible'});
 for(const width of [320,375,768,1440]){
  await page.setViewportSize({width,height:900});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.equal(await page.locator('#delete-collection').isVisible(),true);
 }
 await page.close();
});
