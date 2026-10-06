const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const desktop = path.join(__dirname, "..");
const repo = path.join(desktop, "..");

function run(cmd, args, cwd) {
  const result = spawnSync(cmd, args, { cwd, stdio: "inherit", shell: true });
  if (result.status !== 0) {
    process.exit(result.status || 1);
  }
}

function mustExist(file, hint) {
  if (!fs.existsSync(file)) {
    console.error("Missing", file);
    if (hint) console.error(hint);
    process.exit(1);
  }
}

run("python", [path.join(desktop, "scripts", "make_icon.py")], desktop);
run("node", [path.join(desktop, "scripts", "download-mongo.js")], desktop);
run("npm", ["run", "build"], path.join(repo, "web"));
run("python", ["-m", "PyInstaller", "--noconfirm", "--clean", path.join(desktop, "vay-api.spec")], repo);

mustExist(path.join(repo, "dist", "vay-api", "vay-api.exe"), "PyInstaller did not produce dist/vay-api/vay-api.exe");
mustExist(path.join(desktop, "vendor", "mongo", "mongod.exe"), "Run npm run download-mongo");

// Skip code-sign tool download; Windows often lacks symlink privilege for winCodeSign.
process.env.CSC_IDENTITY_AUTO_DISCOVERY = "false";
run("npx", ["electron-builder", "--win", "nsis"], desktop);

console.log("Installer is in desktop/release/");
