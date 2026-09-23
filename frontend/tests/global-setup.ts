import { rmSync } from 'node:fs'

// Databases from earlier runs are throwaway; clear them so they don't pile up.
export default function globalSetup() {
  rmSync('.e2e', { recursive: true, force: true })
}
