import { defineConfig } from 'vitest/config'

// Unit tests live next to the code as *.test.ts. Playwright owns tests/*.spec.ts.
export default defineConfig({ test: { include: ['src/**/*.test.ts'] } })
