const { spawnSync } = require("child_process");
const path = require("path");

const desktop = path.join(__dirname, "..");

function run(cmd, args, cwd) {
  const result = spawnSync(cmd, args, { cwd, stdio: "inherit", shell: true });
  if (result.status !== 0) {
    process.exit(result.status || 1);
  }
}

if (process.platform !== "darwin") {
  console.error("Mac installers must be built on macOS.");
  process.exit(1);
}

const python = process.env.PYTHON || "python3";
const archFlag = process.arch === "arm64" ? "--arm64" : "--x64";

run(python, [path.join(desktop, "scripts", "make_icon.py")], desktop);
run(
  "npx",
  ["electron-builder", "--mac", "dmg", "pkg", archFlag, "--config", "electron-builder.client.json"],
  desktop,
);

console.log("Client installers are in desktop/release/");
