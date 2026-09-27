import { test, expect } from '@playwright/test'
import { API_URL } from './env'

// Every test starts with no demo data and seeds its own; the suite's database is throwaway.
test.beforeEach(async ({ request }) => {
  await request.delete(`${API_URL}/api/demo`)
})

const seedDemo = (request: import('@playwright/test').APIRequestContext) => request.post(`${API_URL}/api/demo/seed`)

test('builds and compares a complete demo roster', async ({ page, request }) => {
  test.setTimeout(90000)
  await seedDemo(request)
  await page.goto('/')
  await page.getByRole('button', { name: 'Build roster' }).click()
  await expect(page.getByRole('heading', { name: 'Your 26-player roster' })).toBeVisible({ timeout: 30000 })
  await expect(page.getByTestId('roster-player')).toHaveCount(26)
  await expect(page.getByText('Fictional demo data', { exact: true })).toBeVisible()
  await expect(page.getByText('counts 25%').first()).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Saved scenarios' })).toBeVisible()
  await page.getByRole('button', { name: /Demo ·/ }).first().click()
  await expect(page.getByRole('heading', { name: 'Your 26-player roster' })).toBeVisible()
  await page.getByLabel('Payroll limit').fill('140')
  await page.getByRole('button', { name: 'Build roster' }).click()
  await expect(page.getByText('Compare budgets')).toBeVisible({ timeout: 30000 })
})

test('a locked player shows by name, never by raw id', async ({ page, request }) => {
  await seedDemo(request)
  await page.goto('/')
  await page.getByPlaceholder(/Search to lock/).fill('Demo SS 1')
  await page.getByRole('option', { name: /Demo SS 1/ }).click()
  const pill = page.locator('.picker-pill').first()
  await expect(pill).toContainText('Demo SS 1')
  await expect(pill).not.toContainText('#')
  await expect(pill.getByRole('button', { name: /Remove Demo SS 1/ })).toBeVisible()
})

test('a failing coverage request shows a message instead of blanking the app', async ({ page, request }) => {
  await seedDemo(request)
  await page.route('**/api/coverage*', route => route.fulfill({
    status: 404, contentType: 'application/json',
    body: JSON.stringify({ detail: { code: 'missing_players', message: 'Refresh players first' } }),
  }))
  const pageErrors: string[] = []
  page.on('pageerror', error => pageErrors.push(error.message))
  await page.goto('/')
  await page.getByRole('button', { name: /View \d+ missing/ }).click()
  await expect(page.locator('.coverage-drawer [role=alert]')).toContainText('Refresh players first')
  await expect(page.getByRole('link', { name: 'Roster Lab' })).toBeVisible()
  expect(pageErrors).toEqual([])
})

test('demo mode can be exited, and the season list only offers seasons with data', async ({ page, request }) => {
  await seedDemo(request)
  await page.goto('/')
  await expect(page.getByText('Fictional demo data', { exact: true })).toBeVisible()
  await expect(page.locator('select option')).toHaveCount(1)
  await expect(page.getByLabel('Import salary CSV')).toBeDisabled()
  await page.getByRole('button', { name: 'Exit demo' }).click()
  await expect(page.getByText('No player data loaded')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Try demo data' })).toBeVisible()
})

test('the picker is a named combobox, and locks are cleared when their demo data goes away', async ({ page, request }) => {
  await seedDemo(request)
  await page.goto('/')
  const lock = page.getByRole('combobox', { name: 'Lock players', exact: true })
  await lock.fill('Demo SS 1')
  await expect(page.getByRole('option', { name: /Demo SS 1/ })).toBeVisible()
  await lock.press('Enter') // keyboard selection, once the results answer the current query
  await expect(page.locator('.picker-pill')).toHaveCount(1)
  await page.getByRole('button', { name: 'Exit demo' }).click()
  await expect(page.getByText('No player data loaded')).toBeVisible()
  await expect(page.locator('.picker-pill')).toHaveCount(0)
})

test('team logos stay a small badge and never cover the player headshot', async ({ page, request }) => {
  test.setTimeout(90000)
  // A real 1x1 PNG for every external image, so layout is tested without depending on the network.
  const pixel = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=', 'base64')
  await page.route(/espncdn\.com|content\.mlb\.com|mlbstatic\.com/, route => route.fulfill({ status: 200, contentType: 'image/png', body: pixel }))
  await seedDemo(request)
  await page.goto('/')
  await page.getByRole('button', { name: 'Build roster' }).click()
  await expect(page.getByRole('heading', { name: 'Your 26-player roster' })).toBeVisible({ timeout: 30000 })
  const badge = page.locator('.lg-team').first()
  await expect(badge).toBeVisible()
  const badgeBox = await badge.boundingBox()
  expect(badgeBox!.width).toBeLessThanOrEqual(32)
  expect(badgeBox!.height).toBeLessThanOrEqual(32)
  const headshot = page.locator('.lg-photo-wrap > img:not(.lg-team)').first()
  await expect(headshot).toBeVisible()
  // MLB headshots are 2:3 portraits; a wide, short frame crops every face at the nose.
  const photo = (await headshot.boundingBox())!
  expect(photo.width).toBeGreaterThanOrEqual(90)
  expect(photo.height / photo.width).toBeCloseTo(1.5, 1)
})
