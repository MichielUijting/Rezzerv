import { test, expect } from '@playwright/test';

function batchPayload(batchId, lineId, targetLocationId = '') {
  return {
    batch_id: batchId,
    store_provider_code: 'lidl',
    store_label: 'Lidl',
    purchase_date: '2026-08-14',
    import_status: 'review',
    household_id: '0',
    lines: [{
      id: lineId,
      article_name_raw: 'MOSTERD DIJON 250G',
      quantity_raw: 1,
      unit_raw: 'stuk',
      matched_household_article_id: 'household-article-mosterd',
      suggested_household_article_id: 'household-article-mosterd',
      resolved_household_article_name: 'Mosterd Dijon',
      matched_global_product_id: 'global-mosterd',
      matched_global_product_name: 'Mosterd Dijon',
      target_location_id: targetLocationId,
      processing_status: 'pending',
      review_decision: 'selected',
      match_status: 'matched',
    }],
  };
}

async function installUitpakkenMocks(page, { role = 'admin' } = {}) {
  const batchId = `admin-location-${role}`;
  const lineId = `line-${role}`;
  const state = {
    spaces: [{ id: 'space-keuken', naam: 'Keuken', active: true }],
    sublocations: [],
    targetLocationId: '',
    createdSpaces: [],
    createdSublocations: [],
    targetLocationWrites: [],
    handlingOverrideWrites: [],
  };

  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    const json = (body, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    const isAdmin = role === 'admin';
    const permissions = isAdmin
      ? { 'admin.access': true, 'article.create': true, 'receipts.process': true }
      : { 'article.create': true, 'receipts.process': true };

    if (path === '/api/session' && method === 'GET') {
      return json({
        user_id: `user-${role}`,
        email: `${role}@rezzerv.test`,
        active_household_id: '0',
        active_household_name: 'Regressietest huishouden 0',
        display_role: role,
        role,
        membership_count: 1,
        can_switch_households: false,
        memberships: [{ household_id: '0', role }],
        permissions,
        is_viewer: false,
        can_process_receipts: true,
        is_platform_superuser: false,
      });
    }
    if (path === '/api/household' && method === 'GET') {
      return json({
        id: '0',
        active_household_id: '0',
        display_role: role,
        role,
        is_viewer: false,
        permissions,
        store_import_simplification_level: 'gebalanceerd',
      });
    }
    if (path === '/api/store-providers' && method === 'GET') {
      return json([{ code: 'lidl', name: 'Lidl' }]);
    }
    if (path === '/api/store-review-articles' && method === 'GET') {
      return json([{ id: 'household-article-mosterd', name: 'Mosterd Dijon', label: 'Mosterd Dijon' }]);
    }
    if (path === '/api/spaces' && method === 'GET') return json({ items: state.spaces });
    if (path === '/api/sublocations' && method === 'GET') return json({ items: state.sublocations });
    if (path === '/api/spaces' && method === 'POST') {
      const body = request.postDataJSON();
      const created = { id: `space-${state.spaces.length + 1}`, naam: body.naam, active: true };
      state.spaces.push(created);
      state.createdSpaces.push(created);
      return json({ space: created, message: 'Ruimte opgeslagen.' });
    }
    if (path === '/api/sublocations' && method === 'POST') {
      const body = request.postDataJSON();
      const created = { id: `sublocation-${state.sublocations.length + 1}`, naam: body.naam, space_id: body.space_id, active: true };
      state.sublocations.push(created);
      state.createdSublocations.push(created);
      return json({ sublocation: created, message: 'Sublocatie opgeslagen.' });
    }
    if (path === '/api/unpack-start-batches' && method === 'GET') {
      return json({ items: [{ batch_id: batchId, store_provider_code: 'lidl', store_label: 'Lidl', purchase_date: '2026-08-14', inbox_status: 'Gecontroleerd', summary: { total: 1 } }] });
    }
    if (path === `/api/purchase-import-batches/${batchId}` && method === 'GET') {
      return json(batchPayload(batchId, lineId, state.targetLocationId));
    }
    if (path === `/api/purchase-import-lines/${lineId}/target-location` && method === 'POST') {
      const body = request.postDataJSON();
      state.targetLocationId = body.target_location_id || '';
      state.targetLocationWrites.push(body);
      return json({ ok: true, target_location_id: state.targetLocationId });
    }
    if (path === `/api/households/0/articles/inventory-handling/batch` && method === 'POST') {
      return json({ items: [{ id: 'household-article-mosterd', default_inventory_handling: 'STOCK' }] });
    }
    if (path === `/api/households/0/purchase-import-lines/inventory-handling-overrides/batch` && method === 'POST') {
      return json({ items: [] });
    }
    if (path === `/api/households/0/purchase-import-lines/${lineId}/inventory-handling-override` && method === 'PUT') {
      const body = request.postDataJSON();
      state.handlingOverrideWrites.push(body);
      return json({ inventory_handling_override: body.inventory_handling_override });
    }
    if (path === '/api/article-groups' && method === 'GET') return json({ items: [] });
    if (path === '/api/receipts' && method === 'GET') return json([]);
    if (path === '/api/store-connections' && method === 'GET') return json([]);
    if (method === 'GET') return json({ items: [] });
    return json({ ok: true });
  });

  return { batchId, lineId, state };
}

test.describe('Uitpakken Admin locatiebeheer regressie', () => {
  test('Admin voegt vanuit de locatiepicker een locatie toe en die wordt direct geselecteerd', async ({ page }) => {
    const { batchId, lineId, state } = await installUitpakkenMocks(page, { role: 'admin' });

    await page.goto(`/kassabonnen?batch=${batchId}`);
    const locationButton = page.getByTestId(`receipt-line-location-select-${lineId}`);
    await expect(locationButton).toBeVisible();
    expect(await locationButton.evaluate((element) => element.tagName)).toBe('BUTTON');
    await locationButton.click();

    await expect(page.getByRole('dialog', { name: 'Locatie / sublocatie kiezen' })).toBeVisible();
    await expect(page.getByTestId('receipt-location-use-standard')).toBeVisible();
    await expect(page.getByTestId('receipt-location-create-space')).toBeVisible();
    await expect(page.getByTestId('receipt-location-create-sublocation')).toBeVisible();

    await page.getByTestId('receipt-location-create-space').click();
    await page.getByTestId('receipt-location-create-name').fill('Garage');
    await page.getByTestId('receipt-location-create-save').click();

    await expect.poll(() => state.createdSpaces.map((item) => item.naam)).toContain('Garage');
    await expect.poll(() => state.targetLocationWrites.map((item) => item.target_location_id)).toContain('space-2');
    await expect.poll(() => state.handlingOverrideWrites.map((item) => item.inventory_handling_override)).toContain('STOCK');
    await expect(locationButton).toContainText('Garage');
  });

  test('Admin voegt een sublocatie onder de gekozen locatie toe en die wordt direct geselecteerd', async ({ page }) => {
    const { batchId, lineId, state } = await installUitpakkenMocks(page, { role: 'admin' });

    await page.goto(`/kassabonnen?batch=${batchId}`);
    await page.getByTestId(`receipt-line-location-select-${lineId}`).click();

    await page.getByTestId('receipt-location-create-sublocation').click();
    await page.getByTestId('receipt-location-create-parent-space').selectOption('space-keuken');
    await page.getByTestId('receipt-location-create-name').fill('Voorraadkast');
    await page.getByTestId('receipt-location-create-save').click();

    await expect.poll(() => state.createdSublocations.map((item) => `${item.space_id}:${item.naam}`)).toContain('space-keuken:Voorraadkast');
    await expect.poll(() => state.targetLocationWrites.map((item) => item.target_location_id)).toContain('sublocation-1');
    await expect.poll(() => state.handlingOverrideWrites.map((item) => item.inventory_handling_override)).toContain('STOCK');
    await expect(page.getByTestId(`receipt-line-location-select-${lineId}`)).toContainText('Keuken / Voorraadkast');
  });

  test('Gewoon lid krijgt geen locatiebeheeracties in Uitpakken', async ({ page }) => {
    const { batchId, lineId } = await installUitpakkenMocks(page, { role: 'member' });

    await page.goto(`/kassabonnen?batch=${batchId}`);
    await page.getByTestId(`receipt-line-location-select-${lineId}`).click();
    await expect(page.getByRole('dialog', { name: 'Locatie / sublocatie kiezen' })).toBeVisible();

    await expect(page.getByTestId('receipt-location-create-space')).toHaveCount(0);
    await expect(page.getByTestId('receipt-location-create-sublocation')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Beheer locaties', exact: true })).toHaveCount(0);
  });
});