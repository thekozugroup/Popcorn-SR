import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  use: {baseURL:'http://127.0.0.1:18877', viewport:{width:1440,height:1100}},
  webServer: {command:'uv run python scripts/dev-fixture.py', url:'http://127.0.0.1:18877/health', reuseExistingServer: false, timeout:30000},
  reporter: [['list']],
  outputDir: 'evidence/browser-results'
});
