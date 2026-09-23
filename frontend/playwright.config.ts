import { defineConfig } from '@playwright/test'
import path from 'node:path'
import { API_URL, WEB_URL } from './tests/env'

const port = (url: string) => new URL(url).port
// Its own database file: the suite seeds demo data and must never touch data/roster.db.
const e2eDb = path.resolve('.e2e', `roster-${process.pid}.db`)

export default defineConfig({
  testDir: './tests',
  globalSetup: './tests/global-setup.ts',
  use: { baseURL: WEB_URL },
  webServer: [
    {
      command: `..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port ${port(API_URL)}`,
      cwd: '../backend',
      url: `${API_URL}/api/status`,
      env: { ...process.env as Record<string, string>, ROSTER_DB: e2eDb },
      reuseExistingServer: false, // a stale server on this port would silently run against the wrong database
      timeout: 60000,
    },
    {
      command: `npx vite --host 127.0.0.1 --port ${port(WEB_URL)} --strictPort`,
      url: WEB_URL,
      env: { ...process.env as Record<string, string>, VITE_API_URL: API_URL },
      reuseExistingServer: false,
      timeout: 60000,
    },
  ],
})
