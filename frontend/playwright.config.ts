import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { tmpdir } from "node:os";
const root = fileURLToPath(new URL("..", import.meta.url));
const python =
  process.platform === "win32"
    ? ".venv/Scripts/python.exe"
    : ".venv/bin/python";
export default defineConfig({
  testDir: "./tests",
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8000",
    headless: true,
    launchOptions: {
      executablePath: existsSync("/usr/bin/chromium")
        ? "/usr/bin/chromium"
        : undefined,
      args: ["--no-sandbox"],
    },
    trace: "retain-on-failure",
  },
  webServer: {
    command: `"${python}" tools/demo.py --mode simulation --port 8000`,
    cwd: root,
    env: { PBL_DATA_DIR: join(tmpdir(), "pbl4-e2e") },
    url: "http://127.0.0.1:8000/api/health",
    reuseExistingServer: false,
  },
  timeout: 30000,
});
