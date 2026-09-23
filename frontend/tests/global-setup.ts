import { existsSync, readdirSync, rmSync } from 'node:fs'
import { join } from 'node:path'

// Databases from earlier runs are throwaway; clear them so they don't pile up. Playwright starts
// the API before this runs, so keep the file that server is already using (the config names it by pid).
export default function globalSetup() {
  const current = `roster-${process.pid}.db`
  if (!existsSync('.e2e')) return
  for (const name of readdirSync('.e2e')) {
    if (name !== current) rmSync(join('.e2e', name), { force: true })
  }
}
