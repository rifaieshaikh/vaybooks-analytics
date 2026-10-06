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

if (process.platform !== "darwin") {
  console.error("Mac installers must be built on macOS.");
  process.exit(1);
}

const python = process.env.PYTHON || "python3";
const archFlag = process.arch === "arm64" ? "--arm64" : "--x64";

run(python, [path.join(desktop, "scripts", "make_icon.py")], desktop);
run("node", [path.join(desktop, "scripts", "download-mongo.js")], desktop);
run("npm", ["run", "build"], path.join(repo, "web"));
run(python, ["-m", "PyInstaller", "--noconfirm", "--clean", path.join(desktop, "vay-api.spec")], repo);

mustExist(path.join(repo, "dist", "vay-api", "vay-api"), "PyInstaller did not produce dist/vay-api/vay-api");
mustExist(path.join(desktop, "vendor", "mongo", "mongod"), "Run npm run download-mongo");

run("npx", ["electron-builder", "--mac", "dmg", "pkg", archFlag], desktop);

console.log("Installers are in desktop/release/");
