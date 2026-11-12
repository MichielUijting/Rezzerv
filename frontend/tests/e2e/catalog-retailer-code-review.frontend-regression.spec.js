import { test, expect } from '@playwright/test'

test('Catalogus toont afzonderlijke bonartikelnummers per omschrijving en bevestigt exact de gekozen koppeling', async ({ page }) => {
  const product='catalog-butter'
  let reviewed=null
  await page.route('**/api/session', route => route.fulfill({
    status:200, contentType:'application/json',
    body:JSON.stringify({
      user_id:'catalog-editor', active_household_id:'0', context_type:'system',
      role:'owner', display_role:'admin', is_platform_superuser:true,
      permissions:{'platform.catalog.update':true,'platform.external_products.link_existing':true}
    })
  }))
  await page.route('**/api/catalog/catalog-butter', route => route.fulfill({
    status:200,contentType:'application/json',
    body:JSON.stringify({product:{id:product,name:'Ongezouten roomboter',primary_gtin:'20487935'},
      identities:[],household_articles:[],receipt_lines:[]})
  }))
  await page.route('**/api/catalog/catalog-butter/gpc-brick',route => route.fulfill({
    status:200, contentType:'application/json',
    body:JSON.stringify({assignment:null,suggestion:null,suggestions:[]})
  }))
  await page.route('**/api/catalog/catalog-butter/retailer-codes', route => route.fulfill({
    status:200, contentType:'application/json',
    body:JSON.stringify({product:{id:product,name:'Ongezouten roomboter'},
      items:[
        {id:'link-a',retailer_code:'lidl',receipt_text_normalized:'roomboter ongezouten',
         external_article_code:'0095545',primary_gtin:'20487935',status:'confirmed'},
        {id:'link-b',retailer_code:'lidl',receipt_text_normalized:'roomboter ongezouten',
         external_article_code:'6609556',primary_gtin:'20487935',status:'confirmed'},
      ]})
  }))
  await page.route('**/api/catalog/catalog-butter/retailer-codes/review', async route => {
    reviewed=route.request().postDataJSON()
    await route.fulfill({status:200,contentType:'application/json',
      body:JSON.stringify({status:'confirmed',changed:true})})
  })
  await page.goto('/catalogus/catalog-butter')
  const table=page.getByTestId('catalog-retailer-code-table')
  await expect(table).toBeVisible()
  await expect(table.getByText('0095545')).toBeVisible()
  await expect(table.getByText('6609556')).toBeVisible()
  await table.getByRole('button',{name:'Beoordelen'}).first().click()
  await page.getByRole('button',{name:'Bevestigen',exact:true}).click()
  await expect.poll(()=>reviewed?.external_article_code).toBe('0095545')
  expect(reviewed.receipt_text).toBe('roomboter ongezouten')
  expect(reviewed.retailer_code).toBe('lidl')
  expect(reviewed.action).toBe('confirm')
})

test('Geweigerde correctie laat bestaande koppeling zichtbaar en toont centrale foutmelding', async ({page}) => {
  const product='catalog-conflict'
  await page.route('**/api/session', route => route.fulfill({
    status:200,contentType:'application/json',
    body:JSON.stringify({user_id:'editor',active_household_id:'0',role:'owner',
      is_platform_superuser:true,permissions:{'platform.external_products.link_existing':true}})
  }))
  await page.route('**/api/catalog/catalog-conflict',route => route.fulfill({
    status:200,contentType:'application/json',
    body:JSON.stringify({product:{id:product,name:'Broccoli',primary_gtin:'4056489868194'},
      identities:[],household_articles:[],receipt_lines:[]})
  }))
  await page.route('**/api/catalog/catalog-conflict/gpc-brick',route => route.fulfill({
    status:200,contentType:'application/json',body:JSON.stringify({assignment:null,suggestion:null,suggestions:[]})
  }))
  await page.route('**/api/catalog/catalog-conflict/retailer-codes',route => route.fulfill({
    status:200,contentType:'application/json',
    body:JSON.stringify({items:[{id:'l1',retailer_code:'lidl',
      receipt_text_normalized:'broccoli',external_article_code:'0082904',
      primary_gtin:'4056489868194',status:'confirmed'}]})
  }))
  await page.route('**/api/catalog/catalog-conflict/retailer-codes/review',route => route.fulfill({
    status:409,contentType:'application/json',body:JSON.stringify({
      detail:'Er zijn huishoudartikelen gekoppeld aan de huidige productidentiteit.'})
  }))
  await page.goto('/catalogus/catalog-conflict')
  await page.getByTestId('catalog-retailer-code-table').getByRole('button',{name:'Beoordelen'}).click()
  await page.getByRole('textbox',{name:/Andere bevestigde/}).fill('8712345678901')
  await page.getByRole('button',{name:'Correctie controleren'}).click()
  await expect(page.getByText(/Er zijn huishoudartikelen gekoppeld/)).toBeVisible()
  await expect(page.getByTestId('catalog-retailer-code-table').getByText('0082904')).toBeVisible()
})
