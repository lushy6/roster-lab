import { test, expect } from '@playwright/test'

test('builds and compares a complete demo roster', async ({ page, request }) => {
  test.setTimeout(90000)
  await request.post('http://127.0.0.1:8000/api/demo/seed')
  await page.goto('/')
  await page.getByRole('button', { name: 'Build roster' }).click()
  await expect(page.getByRole('heading', { name: 'Your 26-player roster' })).toBeVisible({ timeout: 30000 })
  await expect(page.getByTestId('roster-player')).toHaveCount(26)
  await expect(page.getByText('Fictional demo data', { exact: true })).toBeVisible()
  await page.getByLabel('Payroll limit').fill('140')
  await page.getByRole('button', { name: 'Build roster' }).click()
  await expect(page.getByText('Compare budgets')).toBeVisible({ timeout: 30000 })
})
