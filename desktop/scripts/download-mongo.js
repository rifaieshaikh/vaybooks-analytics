const https = require("https");
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const VERSION = process.env.VAY_MONGO_VERSION || "7.0.16";
const vendor = path.join(__dirname, "..", "vendor");
const destDir = path.join(vendor, "mongo");

function target() {
  if (process.platform === "win32") {
    return {
      url: `https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-${VERSION}.zip`,
      archivePath: path.join(vendor, `mongodb-windows-x86_64-${VERSION}.zip`),
      binaryName: "mongod.exe",
    };
  }
  if (process.platform === "darwin") {
    const arch = process.arch === "arm64" ? "arm64" : "x86_64";
    return {
      url: `https://fastdl.mongodb.org/osx/mongodb-macos-${arch}-${VERSION}.tgz`,
      archivePath: path.join(vendor, `mongodb-macos-${arch}-${VERSION}.tgz`),
      binaryName: "mongod",
    };
  }
  throw new Error("MongoDB download is supported on Windows and macOS only (got " + process.platform + ")");
}

function download(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    const go = (current) => {
      https
        .get(current, (res) => {
          if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
            res.resume();
            go(res.headers.location);
            return;
          }
          if (res.statusCode !== 200) {
            reject(new Error("MongoDB download failed: HTTP " + res.statusCode));
            return;
          }
          const total = Number(res.headers["content-length"] || 0);
          let got = 0;
          res.on("data", (chunk) => {
            got += chunk.length;
            if (total) {
              const pct = ((got / total) * 100).toFixed(0);
              process.stdout.write(`\rDownloading MongoDB ${VERSION}… ${pct}%`);
            }
          });
          res.pipe(file);
          file.on("finish", () => file.close(() => {
            process.stdout.write("\n");
            resolve();
          }));
        })
        .on("error", reject);
    };
    go(url);
  });
}

function extractWindows(zipPath, destExe) {
  fs.mkdirSync(destDir, { recursive: true });
  const ps = `
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead(${JSON.stringify(zipPath)})
try {
  $entry = $zip.Entries | Where-Object { $_.FullName -replace '\\\\','/' -like '*/bin/mongod.exe' } | Select-Object -First 1
  if (-not $entry) { throw 'mongod.exe not found in zip' }
  [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, ${JSON.stringify(destExe)}, $true)
} finally {
  $zip.Dispose()
}
`;
  const result = spawnSync("powershell", ["-NoProfile", "-Command", ps], { stdio: "inherit" });
  if (result.status !== 0) {
    throw new Error("Failed to extract mongod.exe");
  }
}

function findBinMongod(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      const found = findBinMongod(full);
      if (found) return found;
      continue;
    }
    const normalized = full.replace(/\\/g, "/");
    if (entry.name === "mongod" && normalized.endsWith("/bin/mongod")) return full;
  }
  return "";
}

function extractDarwin(archivePath, destBin) {
  const tmp = path.join(vendor, "mongo-extract");
  fs.rmSync(tmp, { recursive: true, force: true });
  fs.mkdirSync(tmp, { recursive: true });
  const result = spawnSync("tar", ["-xzf", archivePath, "-C", tmp], { stdio: "inherit" });
  if (result.status !== 0) {
    throw new Error("Failed to extract mongod");
  }
  const found = findBinMongod(tmp);
  if (!found) {
    throw new Error("mongod not found in tarball");
  }
  fs.mkdirSync(destDir, { recursive: true });
  fs.copyFileSync(found, destBin);
  fs.chmodSync(destBin, 0o755);
  fs.rmSync(tmp, { recursive: true, force: true });
}

async function main() {
  const spec = target();
  const destBin = path.join(destDir, spec.binaryName);
  if (fs.existsSync(destBin)) {
    console.log(spec.binaryName + " already present at", destBin);
    return;
  }
  fs.mkdirSync(vendor, { recursive: true });
  if (!fs.existsSync(spec.archivePath)) {
    console.log("Fetching", spec.url);
    await download(spec.url, spec.archivePath);
  }
  if (process.platform === "win32") extractWindows(spec.archivePath, destBin);
  else extractDarwin(spec.archivePath, destBin);
  if (!fs.existsSync(destBin)) {
    throw new Error(spec.binaryName + " missing after extract");
  }
  console.log("Installed", destBin);
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
