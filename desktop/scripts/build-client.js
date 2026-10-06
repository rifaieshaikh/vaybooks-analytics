const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const desktop = path.join(__dirname, "..");

function run(cmd, args, cwd) {
  const result = spawnSync(cmd, args, { cwd, stdio: "inherit", shell: true });
  if (result.status !== 0) {
    process.exit(result.status || 1);
  }
}

run("python", [path.join(desktop, "scripts", "make_icon.py")], desktop);

process.env.CSC_IDENTITY_AUTO_DISCOVERY = "false";
run(
  "npx",
  ["electron-builder", "--win", "nsis", "--config", "electron-builder.client.json"],
  desktop,
);

console.log("Client installer is in desktop/release/");
