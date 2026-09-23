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
