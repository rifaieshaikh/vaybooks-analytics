const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("vayTabs", {
  list: () => ipcRenderer.invoke("tabs:list"),
  newTab: () => ipcRenderer.invoke("tabs:new"),
  activate: (id) => ipcRenderer.invoke("tabs:activate", id),
  close: (id) => ipcRenderer.invoke("tabs:close", id),
  onChange: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("tabs-changed", listener);
    return () => ipcRenderer.removeListener("tabs-changed", listener);
  },
});
