const { app, BaseWindow, BrowserWindow, WebContentsView, Tray, Menu, nativeImage, clipboard, dialog, shell, ipcMain } = require("electron");
const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const http = require("http");
const https = require("https");
const net = require("net");
const path = require("path");
const { URL } = require("url");

const PORT = Number(process.env.VAY_PORT || 8765);
const MONGO_PORT = Number(process.env.VAY_MONGO_PORT || 27018);
const DEFAULT_HOST_UI = `http://127.0.0.1:${PORT}`;

const TAB_BAR_HEIGHT = 42;

let mainWindow = null;
let chromeView = null;
let splashView = null;
let tabs = [];
let activeTabId = null;
let tabSeq = 0;
let tray = null;
let mongoProc = null;
let apiProc = null;
let quitting = false;
let lanUrls = [];
let startedChildren = false;
let ownsLocalStack = false;
let clientMode = false;
let serverUrl = DEFAULT_HOST_UI;

function userDataDir() {
  return app.getPath("userData");
}

function iconPath() {
  const packaged = path.join(process.resourcesPath, "icon.png");
  const dev = path.join(__dirname, "build", "icon.png");
  if (fs.existsSync(packaged)) return packaged;
  if (fs.existsSync(dev)) return dev;
  return "";
}

function nativeExecutable(name) {
  return process.platform === "win32" ? name + ".exe" : name;
}

function mongodPath() {
  const file = nativeExecutable("mongod");
  const packaged = path.join(process.resourcesPath, "mongo", file);
  const dev = path.join(__dirname, "vendor", "mongo", file);
  if (fs.existsSync(packaged)) return packaged;
  if (fs.existsSync(dev)) return dev;
  return "";
}

function apiExePath() {
  return path.join(process.resourcesPath, "vay-api", nativeExecutable("vay-api"));
}

function clientMarkerPath() {
  return path.join(process.resourcesPath, "client.marker");
}

function isClientMode() {
  if (process.env.VAY_CLIENT === "1" || process.env.VAY_CLIENT === "true") return true;
  return app.isPackaged && fs.existsSync(clientMarkerPath());
}

function configPaths() {
  const paths = [path.join(userDataDir(), "server.json")];
  if (app.isPackaged) {
    paths.push(path.join(process.resourcesPath, "config.json"));
    paths.push(path.join(path.dirname(process.execPath), "config.json"));
  } else {
    paths.push(path.join(__dirname, "config.json"));
  }
  return paths;
}

function normalizeServerUrl(raw) {
  const text = String(raw || "").trim().replace(/\/+$/, "");
  if (!text) return "";
  let withScheme = text;
  if (!/^https?:\/\//i.test(withScheme)) withScheme = "http://" + withScheme;
  const parsed = new URL(withScheme);
  if (!parsed.hostname) throw new Error("Server URL needs a host.");
  return parsed.origin;
}

function readServerConfig() {
  if (process.env.VAY_SERVER_URL) {
    try {
      return normalizeServerUrl(process.env.VAY_SERVER_URL);
    } catch {
      /* fall through */
    }
  }
  for (const file of configPaths()) {
    if (!fs.existsSync(file)) continue;
    try {
      const data = JSON.parse(fs.readFileSync(file, "utf8"));
      const url = normalizeServerUrl(data.serverUrl || data.url || data.apiUrl || "");
      if (url) return url;
    } catch {
      /* try next */
    }
  }
  return "";
}

function writeServerConfig(url) {
  const file = path.join(userDataDir(), "server.json");
  fs.mkdirSync(userDataDir(), { recursive: true });
  fs.writeFileSync(file, JSON.stringify({ serverUrl: url }, null, 2), "utf8");
}

function showUrlInputWindow(initial) {
  return new Promise((resolve) => {
    const win = new BrowserWindow({
      width: 480,
      height: 220,
      resizable: false,
      minimizable: false,
      maximizable: false,
      parent: mainWindow || undefined,
      modal: !!mainWindow,
      show: true,
      autoHideMenuBar: true,
      title: "Backend server URL",
      webPreferences: {
        preload: path.join(__dirname, "preload-config.js"),
        contextIsolation: true,
        nodeIntegration: false,
      },
    });
    win.setMenu(null);
    win.setMenuBarVisibility(false);
    const html = `<!doctype html>
<html><head><meta charset="UTF-8"/><style>
body{font-family:"Segoe UI",system-ui,sans-serif;margin:24px;background:#0f3d2e;color:#fff}
label{display:block;margin-bottom:8px;color:#d6e4de}
input{width:100%;box-sizing:border-box;padding:10px 12px;border-radius:8px;border:1px solid #2a5c4a;background:#0a2a20;color:#fff;font-size:14px}
.row{display:flex;gap:8px;justify-content:flex-end;margin-top:16px}
button{padding:8px 14px;border-radius:8px;border:0;cursor:pointer;font-weight:600}
.primary{background:#3dd68c;color:#0a2a20}
.ghost{background:transparent;color:#d6e4de;border:1px solid #2a5c4a}
</style></head><body>
<label for="url">Backend server URL</label>
<input id="url" value="${String(initial).replace(/"/g, "&quot;")}" autofocus />
<div class="row">
  <button class="ghost" id="cancel">Cancel</button>
  <button class="primary" id="ok">Save</button>
</div>
<script>
  const send = (v) => window.vayConfig && window.vayConfig.submit(v);
  document.getElementById("ok").onclick = () => send(document.getElementById("url").value);
  document.getElementById("cancel").onclick = () => send(null);
  document.getElementById("url").addEventListener("keydown", (e) => {
    if (e.key === "Enter") send(document.getElementById("url").value);
    if (e.key === "Escape") send(null);
  });
</script>
</body></html>`;
    win.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(html));
    const channel = "vay-config-submit";
    const onSubmit = (_event, value) => {
      ipcMain.removeListener(channel, onSubmit);
      if (!win.isDestroyed()) win.close();
      resolve(value);
    };
    ipcMain.on(channel, onSubmit);
    win.on("closed", () => {
      ipcMain.removeListener(channel, onSubmit);
      resolve(null);
    });
  });
}

function portOpen(port) {
  return new Promise((resolve) => {
    const socket = net.connect({ port, host: "127.0.0.1" }, () => {
      socket.end();
      resolve(true);
    });
    socket.on("error", () => resolve(false));
    socket.setTimeout(400, () => {
      socket.destroy();
      resolve(false);
    });
  });
}

function waitPort(port, timeoutMs) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const socket = net.connect({ port, host: "127.0.0.1" }, () => {
        socket.end();
        resolve();
      });
      socket.on("error", () => {
        socket.destroy();
        if (Date.now() - start > timeoutMs) reject(new Error("Timed out waiting for port " + port));
        else setTimeout(attempt, 300);
      });
    };
    attempt();
  });
}

function httpGet(url, timeoutMs = 2000) {
  return new Promise((resolve) => {
    let parsed;
    try {
      parsed = new URL(url);
    } catch {
      resolve({ ok: false, status: 0, body: "" });
      return;
    }
    const lib = parsed.protocol === "https:" ? https : http;
    const req = lib.get(url, (res) => {
      let body = "";
      res.on("data", (chunk) => {
        body += chunk;
      });
      res.on("end", () => resolve({ ok: res.statusCode >= 200 && res.statusCode < 300, status: res.statusCode, body }));
    });
    req.on("error", () => resolve({ ok: false, status: 0, body: "" }));
    req.setTimeout(timeoutMs, () => {
      req.destroy();
      resolve({ ok: false, status: 0, body: "" });
    });
  });
}

function healthOk(base = serverUrl) {
  return httpGet(`${base.replace(/\/+$/, "")}/api/health`).then((r) => r.ok && r.status === 200);
}

function waitHealth(timeoutMs, base = serverUrl) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const attempt = async () => {
      if (await healthOk(base)) {
        resolve();
        return;
      }
      if (Date.now() - start > timeoutMs) reject(new Error("The API did not become ready."));
      else setTimeout(attempt, 400);
    };
    attempt();
  });
}

function fetchInfo(base = serverUrl) {
  return httpGet(`${base.replace(/\/+$/, "")}/api/info`).then((r) => {
    if (!r.ok) return null;
    try {
      return JSON.parse(r.body);
    } catch {
      return null;
    }
  });
}

function logPath(name) {
  return path.join(userDataDir(), name);
}

function openLog(name) {
  const file = logPath(name);
  return fs.openSync(file, "a");
}

function refreshTrayMenu() {
  if (!tray) return;
  buildTray(true);
}

function notifyChildDied(kind) {
  const detail =
    kind +
    " stopped unexpectedly. Use the tray menu to open logs under:\n" +
    userDataDir();
  if (tray && typeof tray.displayBalloon === "function") {
    try {
      tray.displayBalloon({
        title: "Vay Reports",
        content: kind + " stopped. Open logs from the tray menu.",
      });
    } catch {
      /* optional on some platforms */
    }
  }
  if (mainWindow && !mainWindow.isDestroyed()) {
    dialog.showMessageBox(mainWindow, {
      type: "warning",
      title: "Vay Reports",
      message: kind + " stopped",
      detail,
    }).catch(() => {});
  }
  refreshTrayMenu();
}

function startMongo() {
  const exe = mongodPath();
  if (!exe) return false;
  const dbPath = path.join(userDataDir(), "db");
  fs.mkdirSync(dbPath, { recursive: true });
  const log = openLog("mongo.log");
  mongoProc = spawn(
    exe,
    [
      "--dbpath",
      dbPath,
      "--port",
      String(MONGO_PORT),
      "--bind_ip",
      "127.0.0.1",
      "--logpath",
      path.join(userDataDir(), "mongod.log"),
      "--directoryperdb",
    ],
    { windowsHide: true, stdio: ["ignore", log, log] },
  );
  startedChildren = true;
  mongoProc.on("exit", (code) => {
    if (!quitting && code && code !== 0) {
      console.error("mongod exited", code);
      notifyChildDied("MongoDB");
    }
  });
  return true;
}

function apiEnv() {
  return {
    ...process.env,
    VAY_HOST: "0.0.0.0",
    VAY_PORT: String(PORT),
    MONGODB_URI: process.env.MONGODB_URI || `mongodb://127.0.0.1:${MONGO_PORT}/vay-reports`,
    VAY_DATA_DIR: userDataDir(),
    VAY_EXPORT_DIR: path.join(userDataDir(), "exports"),
  };
}

function bundledUiMarker() {
  const candidates = [
    path.join(process.resourcesPath, "vay-api", "_internal", "web", "dist", "index.html"),
    path.join(__dirname, "..", "web", "dist", "index.html"),
  ];
  for (const file of candidates) {
    if (!fs.existsSync(file)) continue;
    const match = fs.readFileSync(file, "utf8").match(/assets\/index-[A-Za-z0-9_-]+\.js/);
    if (match) return match[0];
  }
  return "";
}

function processImageName(pid) {
  if (process.platform === "darwin") {
    const result = spawnSync("ps", ["-p", String(pid), "-o", "comm="], { encoding: "utf8" });
    return String(result.stdout || "").trim();
  }
  if (process.platform !== "win32") return "";
  const result = spawnSync("tasklist", ["/FI", "PID eq " + pid, "/FO", "CSV", "/NH"], {
    encoding: "utf8",
    windowsHide: true,
  });
  const match = String(result.stdout || "").match(/^"([^"]+)"/);
  return match ? match[1] : "";
}

async function runningUiMatchesBundle() {
  const marker = bundledUiMarker();
  if (!marker) return true;
  const page = await httpGet(DEFAULT_HOST_UI + "/");
  return page.ok && page.body.includes(marker);
}

async function stopStaleApi() {
  for (const pid of pidsListening(PORT)) {
    if (!/vay-api(\.exe)?$/i.test(processImageName(pid))) continue;
    killPidTree(pid);
  }
  const start = Date.now();
  while (Date.now() - start < 8000) {
    if (!(await portOpen(PORT))) return;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
}

function startApi() {
  const log = openLog("api.log");
  const env = apiEnv();
  startedChildren = true;
  if (app.isPackaged) {
    const exe = apiExePath();
    if (!fs.existsSync(exe)) throw new Error("vay-api is missing from the install.");
    apiProc = spawn(exe, [], { env, windowsHide: true, cwd: path.dirname(exe), stdio: ["ignore", log, log] });
  } else {
    const root = path.join(__dirname, "..");
    const py = process.env.PYTHON || "python";
    apiProc = spawn(py, ["-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", String(PORT)], {
      env,
      cwd: root,
      windowsHide: true,
      stdio: ["ignore", log, log],
    });
  }
  apiProc.on("exit", (code) => {
    if (!quitting && code && code !== 0) {
      console.error("api exited", code);
      notifyChildDied("API");
    }
  });
}

function killPidTree(pid) {
  const id = Number(pid);
  if (!id) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(id), "/t", "/f"], { windowsHide: true, stdio: "ignore" });
    return;
  }
  try {
    process.kill(id, "SIGTERM");
  } catch {
    /* already gone */
  }
}

function pidsListening(port) {
  if (process.platform === "darwin") {
    const result = spawnSync("lsof", ["-nP", "-iTCP:" + String(port), "-sTCP:LISTEN", "-t"], {
      encoding: "utf8",
    });
    const found = new Set();
    for (const line of String(result.stdout || "").split(/\r?\n/)) {
      const pid = Number(line.trim());
      if (pid && pid !== process.pid) found.add(pid);
    }
    return [...found];
  }
  if (process.platform !== "win32") return [];
  const result = spawnSync("netstat", ["-ano", "-p", "tcp"], { encoding: "utf8", windowsHide: true });
  const found = new Set();
  const needle = ":" + String(port);
  for (const line of String(result.stdout || "").split(/\r?\n/)) {
    const parts = line.trim().split(/\s+/);
    if (parts.length < 5 || parts[3] !== "LISTENING") continue;
    if (!parts[1].endsWith(needle)) continue;
    const pid = Number(parts[4]);
    if (pid && pid !== process.pid) found.add(pid);
  }
  return [...found];
}

function stopChild(child) {
  if (!child || !child.pid) return;
  killPidTree(child.pid);
}

function stopChildren() {
  const apiPid = apiProc && apiProc.pid;
  const mongoPid = mongoProc && mongoProc.pid;
  stopChild(apiProc);
  stopChild(mongoProc);
  if (ownsLocalStack) {
    for (const pid of pidsListening(PORT)) {
      if (pid !== apiPid) killPidTree(pid);
    }
    for (const pid of pidsListening(MONGO_PORT)) {
      if (pid !== mongoPid) killPidTree(pid);
    }
  }
  apiProc = null;
  mongoProc = null;
}

function showWindow() {
  if (!mainWindow) return;
  mainWindow.show();
  mainWindow.focus();
  layoutViews();
}

function buildTray(reuse) {
  const file = iconPath();
  const image = file ? nativeImage.createFromPath(file) : nativeImage.createEmpty();
  if (!reuse || !tray) {
    tray = new Tray(
      image.isEmpty()
        ? nativeImage.createFromDataURL(
            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
          )
        : image,
    );
    tray.on("click", showWindow);
  }
  const lanItems = lanUrls.length
    ? lanUrls.map((url) => ({
        label: url,
        click: () => {
          clipboard.writeText(url);
        },
      }))
    : [{ label: "LAN address not ready", enabled: false }];

  const template = [{ label: "Open Vay Reports", click: showWindow }, { type: "separator" }];
  if (clientMode) {
    template.push(
      {
        label: "Server: " + serverUrl,
        enabled: false,
      },
      {
        label: "Change server…",
        click: () => changeServerInteractive(),
      },
      { label: "Open in browser", click: () => shell.openExternal(serverUrl) },
    );
  } else {
    template.push(
      { label: "LAN (copy)", submenu: lanItems },
      { label: "Open in browser", click: () => shell.openExternal(serverUrl) },
      { type: "separator" },
      {
        label: "Open API log",
        click: () => shell.openPath(logPath("api.log")),
      },
      {
        label: "Open Mongo log",
        click: () => shell.openPath(logPath("mongo.log")),
      },
    );
  }
  template.push(
    { type: "separator" },
    {
      label: "Quit",
      click: () => {
        quitting = true;
        app.quit();
      },
    },
  );
  tray.setToolTip(clientMode ? "Vay Reports (client)" : "Vay Reports");
  tray.setContextMenu(Menu.buildFromTemplate(template));
}

function tabPayload() {
  return {
    activeId: activeTabId,
    tabs: tabs.map((tab) => ({ id: tab.id, title: tab.title })),
  };
}

function pushTabs() {
  if (!chromeView || chromeView.webContents.isDestroyed()) return;
  chromeView.webContents.send("tabs-changed", tabPayload());
}

function layoutViews() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const { width, height } = mainWindow.getContentBounds();
  if (splashView) {
    splashView.setBounds({ x: 0, y: 0, width, height });
    return;
  }
  const contentHeight = Math.max(0, height - TAB_BAR_HEIGHT);
  for (const tab of tabs) {
    tab.view.setBounds({ x: 0, y: TAB_BAR_HEIGHT, width, height: contentHeight });
    tab.view.setVisible(tab.id === activeTabId);
  }
  if (chromeView) {
    chromeView.setBounds({ x: 0, y: 0, width, height: TAB_BAR_HEIGHT });
    mainWindow.contentView.addChildView(chromeView);
  }
}

function bindTabKeys(webContents) {
  webContents.on("before-input-event", (event, input) => {
    if (input.type !== "keyDown") return;
    const mod = input.control || input.meta;
    const key = String(input.key || "").toLowerCase();
    if (mod && key === "t" && !input.shift && !input.alt) {
      event.preventDefault();
      addTab(serverUrl);
      return;
    }
    if (mod && key === "w" && !input.shift && !input.alt) {
      event.preventDefault();
      if (activeTabId) closeTab(activeTabId);
      return;
    }
    if (input.control && input.key === "Tab") {
      event.preventDefault();
      cycleTab(input.shift ? -1 : 1);
    }
  });
}

function ensureChrome() {
  if (chromeView || !mainWindow || mainWindow.isDestroyed()) return;
  chromeView = new WebContentsView({
    webPreferences: {
      preload: path.join(__dirname, "preload-tabs.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.contentView.addChildView(chromeView);
  bindTabKeys(chromeView.webContents);
  chromeView.webContents.on("did-finish-load", () => pushTabs());
  chromeView.webContents.loadFile(path.join(__dirname, "tabs.html"));
}

function attachContent(view) {
  const wc = view.webContents;
  wc.setWindowOpenHandler(({ url }) => {
    addTab(url);
    return { action: "deny" };
  });
  wc.on("page-title-updated", (_event, title) => {
    const tab = tabs.find((item) => item.view === view);
    if (!tab) return;
    tab.title = title || "Vay Reports";
    if (tab.id === activeTabId && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.title = tab.title;
    }
    pushTabs();
  });
  bindTabKeys(wc);
}

function addTab(url) {
  if (!mainWindow || mainWindow.isDestroyed()) return null;
  ensureChrome();
  const view = new WebContentsView({
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  const tab = {
    id: String(++tabSeq),
    title: "Vay Reports",
    view,
  };
  tabs.push(tab);
  mainWindow.contentView.addChildView(view);
  attachContent(view);
  const target = url || serverUrl;
  tab.pending = view.webContents.session.clearCache().catch(() => {}).then(() => view.webContents.loadURL(target));
  tab.pending.catch(() => {
    if (tabs.includes(tab)) {
      tab.title = "Failed to load";
      pushTabs();
    }
  });
  activateTab(tab.id);
  return tab;
}

function activateTab(id) {
  if (!tabs.some((tab) => tab.id === id)) return;
  activeTabId = id;
  layoutViews();
  const tab = tabs.find((item) => item.id === id);
  if (tab && mainWindow && !mainWindow.isDestroyed()) mainWindow.title = tab.title;
  if (tab && !tab.view.webContents.isDestroyed()) tab.view.webContents.focus();
  pushTabs();
}

function closeTab(id) {
  const index = tabs.findIndex((tab) => tab.id === id);
  if (index < 0) return;
  if (tabs.length === 1) {
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.hide();
    return;
  }
  const [tab] = tabs.splice(index, 1);
  mainWindow.contentView.removeChildView(tab.view);
  if (!tab.view.webContents.isDestroyed()) tab.view.webContents.close();
  if (activeTabId === id) {
    const next = tabs[Math.min(index, tabs.length - 1)];
    activeTabId = next.id;
  }
  layoutViews();
  const active = tabs.find((item) => item.id === activeTabId);
  if (active && !active.view.webContents.isDestroyed()) active.view.webContents.focus();
  pushTabs();
}

function cycleTab(delta) {
  if (tabs.length < 2) return;
  const index = tabs.findIndex((tab) => tab.id === activeTabId);
  const next = (index + delta + tabs.length) % tabs.length;
  activateTab(tabs[next].id);
}

function removeSplash() {
  if (!splashView || !mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.contentView.removeChildView(splashView);
  if (!splashView.webContents.isDestroyed()) splashView.webContents.close();
  splashView = null;
}

async function showApp(url) {
  removeSplash();
  ensureChrome();
  if (!tabs.length) {
    const tab = addTab(url);
    if (tab && tab.pending) await tab.pending;
    return;
  }
  layoutViews();
  pushTabs();
}

async function reloadAllTabs(url) {
  await Promise.all(
    tabs.map((tab) => {
      tab.title = "Vay Reports";
      return tab.view.webContents.session.clearCache().catch(() => {}).then(() => tab.view.webContents.loadURL(url));
    }),
  );
  pushTabs();
}

function registerTabIpc() {
  ipcMain.handle("tabs:list", () => tabPayload());
  ipcMain.handle("tabs:new", () => {
    const tab = addTab(serverUrl);
    return tab ? tab.id : null;
  });
  ipcMain.handle("tabs:activate", (_event, id) => {
    activateTab(String(id));
  });
  ipcMain.handle("tabs:close", (_event, id) => {
    closeTab(String(id));
  });
}

function createWindow(splashText) {
  const file = iconPath();
  mainWindow = new BaseWindow({
    width: 1360,
    height: 860,
    minWidth: 960,
    minHeight: 640,
    show: false,
    backgroundColor: "#0f3d2e",
    icon: file || undefined,
  });
  mainWindow.setMenu(null);
  mainWindow.setMenuBarVisibility(false);
  splashView = new WebContentsView({
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.contentView.addChildView(splashView);
  const splash = path.join(__dirname, "splash.html");
  if (splashText) {
    const html = fs.readFileSync(splash, "utf8").replace(
      /Starting MongoDB and the local server…/,
      splashText,
    );
    splashView.webContents.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(html));
  } else {
    splashView.webContents.loadFile(splash);
  }
  const reveal = () => {
    if (!mainWindow || mainWindow.isDestroyed() || mainWindow.isVisible()) return;
    layoutViews();
    mainWindow.show();
  };
  splashView.webContents.once("did-finish-load", reveal);
  mainWindow.on("resize", layoutViews);
  mainWindow.on("show", layoutViews);
  mainWindow.on("maximize", layoutViews);
  mainWindow.on("unmaximize", layoutViews);
  mainWindow.on("enter-full-screen", layoutViews);
  mainWindow.on("leave-full-screen", layoutViews);
  mainWindow.on("close", (event) => {
    if (quitting) return;
    event.preventDefault();
    quitting = true;
    app.quit();
  });
}

async function ensureMongo() {
  if (await portOpen(MONGO_PORT)) return;
  if (mongodPath()) {
    if (!startMongo()) {
      throw new Error("Could not start the bundled MongoDB server.");
    }
    await waitPort(MONGO_PORT, 45000);
    return;
  }
  if ((await portOpen(27017)) && !process.env.MONGODB_URI) {
    process.env.MONGODB_URI = "mongodb://127.0.0.1:27017/vay-reports";
    return;
  }
  throw new Error(
    "MongoDB was not found. Run npm run download-mongo in desktop/, or install MongoDB and leave it running.",
  );
}

async function ensureApi() {
  if (await healthOk(DEFAULT_HOST_UI)) {
    if (await runningUiMatchesBundle()) return;
    await stopStaleApi();
  }
  startApi();
  await waitHealth(60000, DEFAULT_HOST_UI);
}

async function resolveClientServerUrl() {
  let url = readServerConfig();
  while (true) {
    if (!url) {
      const entered = await showUrlInputWindow("http://127.0.0.1:8765");
      if (entered == null) throw new Error("Server URL is required for the client install.");
      try {
        url = normalizeServerUrl(entered);
      } catch (err) {
        await dialog.showMessageBox(mainWindow, {
          type: "error",
          title: "Vay Reports",
          message: "Invalid server URL",
          detail: String(err.message || err),
        });
        url = "";
        continue;
      }
    }
    if (await healthOk(url)) {
      writeServerConfig(url);
      return url;
    }
    const choice = await dialog.showMessageBox(mainWindow, {
      type: "error",
      buttons: ["Try again", "Change URL", "Quit"],
      defaultId: 1,
      cancelId: 2,
      title: "Vay Reports",
      message: "Could not reach the backend",
      detail: `No healthy response from ${url}/api/health.\nStart the server app (or Docker/API) and check the address.`,
    });
    if (choice.response === 2) throw new Error("Cancelled.");
    if (choice.response === 1) url = "";
  }
}

async function changeServerInteractive() {
  const entered = await showUrlInputWindow(serverUrl);
  if (entered == null) return;
  let next;
  try {
    next = normalizeServerUrl(entered);
  } catch (err) {
    await dialog.showMessageBox(mainWindow, {
      type: "error",
      title: "Vay Reports",
      message: "Invalid server URL",
      detail: String(err.message || err),
    });
    return;
  }
  if (!(await healthOk(next))) {
    await dialog.showMessageBox(mainWindow, {
      type: "error",
      title: "Vay Reports",
      message: "Could not reach the backend",
      detail: `No healthy response from ${next}/api/health.`,
    });
    return;
  }
  serverUrl = next;
  writeServerConfig(next);
  buildTray();
  if (!tabs.length) await showApp(serverUrl);
  else await reloadAllTabs(serverUrl);
}

async function bootClient() {
  createWindow("Connecting to the configured backend…");
  try {
    serverUrl = await resolveClientServerUrl();
    const info = await fetchInfo(serverUrl);
    lanUrls = (info && info.lan_urls) || [];
    buildTray();
    await showApp(serverUrl);
  } catch (err) {
    await dialog.showMessageBox(mainWindow, {
      type: "error",
      title: "Vay Reports",
      message: "Could not connect to the backend.",
      detail: String(err && err.message ? err.message : err),
    });
    quitting = true;
    app.quit();
  }
}

async function bootServer() {
  ownsLocalStack = true;
  createWindow();
  try {
    serverUrl = DEFAULT_HOST_UI;
    await ensureMongo();
    await ensureApi();
    const info = await fetchInfo(serverUrl);
    lanUrls = (info && info.lan_urls) || [];
    buildTray();
    await showApp(serverUrl);
  } catch (err) {
    await dialog.showMessageBox(mainWindow, {
      type: "error",
      title: "Vay Reports",
      message: "Could not start the local server.",
      detail: String(err && err.message ? err.message : err),
    });
    quitting = true;
    app.quit();
  }
}

async function boot() {
  clientMode = isClientMode();
  if (clientMode) await bootClient();
  else await bootServer();
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", showWindow);
  app.setName(isClientMode() ? "Vay Reports Client" : "Vay Reports");
  app.whenReady().then(() => {
    Menu.setApplicationMenu(null);
    registerTabIpc();
    return boot();
  });
}

app.on("before-quit", () => {
  quitting = true;
  if (ownsLocalStack || startedChildren) stopChildren();
});

app.on("window-all-closed", () => {
  if (!quitting) app.quit();
});
