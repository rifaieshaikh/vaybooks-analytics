const { spawn } = require("child_process");
const path = require("path");

const electron = require("electron");
const desktop = path.join(__dirname, "..");

const child = spawn(electron, ["."], {
  stdio: "inherit",
  env: { ...process.env, VAY_CLIENT: "1" },
  cwd: desktop,
  windowsHide: false,
});

child.on("exit", (code) => process.exit(code || 0));
