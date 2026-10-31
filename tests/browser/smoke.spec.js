// CI-only Chromium smoke tests. All application/model modes remain offline.
const {test,expect}=require('@playwright/test');
test.beforeEach(async({context,page})=>{
  await context.route('**/*',route=>{
    const url=new URL(route.request().url());
    return url.protocol==='http:'&&url.hostname==='127.0.0.1'&&url.port==='8765'?route.continue():route.abort();
  });
  page.on('pageerror',error=>{throw error});
});

test('everyday evidence, uncertainty, bounded agent and legacy replay',async({page})=>{
  const errors=[];page.on('console',message=>{if(message.type()==='error')errors.push(message.text())});
  const response=await page.goto('/');
  expect(response.headers()['content-security-policy']).toContain('script-src \'sha256-');
  await page.getByRole('button',{name:'Find matching text ↗',exact:true}).click();
  await expect(page.locator('#rag-result')).toContainText('receipt');
  await expect(page.locator('#rag-result')).toContainText('returns:1');
  await page.getByRole('button',{name:'Ask about an unmentioned item',exact:true}).click();
  await page.getByRole('button',{name:'Find matching text ↗',exact:true}).click();
  await expect(page.locator('#rag-result')).toContainText('couldn’t find enough');
  await page.getByRole('tab',{name:'02Agents',exact:true}).click();
  await page.getByRole('button',{name:'Run walkthrough ↗',exact:true}).click();
  await expect(page.locator('#bounded-result')).toContainText('completed');
  await expect(page.locator('#bounded-result')).toContainText('no model inference');
  await page.locator('#bounded-result summary').click();
  await expect(page.locator('#bounded-result')).toContainText('"model_requests": 0');
  await expect(page.locator('#bounded-result')).toContainText('"scripted_decisions": 3');
  await page.getByRole('tab',{name:'03Serving',exact:true}).click();
  await page.getByRole('button',{name:'Run synthetic replay ↗',exact:true}).click();
  await expect(page.locator('#serving-result')).toContainText('synthetic replay');
  await expect(page.locator('#serving-result')).toContainText('Unavailable');
  await page.getByRole('button',{name:'Inspect synthetic batch ↗',exact:true}).click();
  await expect(page.locator('#suite-result')).toContainText('SYNTHETIC');
  await expect(page.locator('#suite-result')).toContainText('9/9');
  await page.getByRole('button',{name:'Inspect synthetic batch ↗',exact:true}).click();
  await expect(page.locator('#suite-result .stats')).toHaveCount(1);
  await page.getByRole('link',{name:'How the batch is measured →',exact:true}).click();
  await expect(page).toHaveURL(/#docs\/serving-suite$/);
  await page.reload();
  await expect(page.getByRole('heading',{name:'Measure a batch fairly',exact:true})).toBeVisible();
  await page.getByRole('link',{name:'Local use & security',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Keep the lab on your machine.',exact:true})).toBeVisible();
  await page.getByRole('link',{name:'Return to the offline demos →',exact:true}).click();
  await expect(page).toHaveURL(/#rag$/);expect(errors).toEqual([]);
});

for(const width of [320,390]){
  test(`mobile ${width}: batch and documentation fit`,async({page})=>{
    await page.setViewportSize({width,height:844});
    await page.goto('/#serving');
    await page.getByRole('button',{name:'Inspect synthetic batch ↗',exact:true}).click();
    await expect(page.locator('#suite-result')).toContainText('nearest rank');
    await page.locator('#suite-result summary').click();
    await expect(page.locator('#suite-result details')).toHaveAttribute('open','');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(width);
    await page.getByRole('link',{name:'How the batch is measured →',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Measure a batch fairly',exact:true})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(width);
    await page.getByRole('link',{name:'Open the batch demo →',exact:true}).click();
    await expect(page.locator('#suite-result')).toContainText('invented');
  });
}
