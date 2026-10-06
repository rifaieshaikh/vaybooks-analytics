const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("vayConfig", {
  submit: (value) => ipcRenderer.send("vay-config-submit", value),
});
