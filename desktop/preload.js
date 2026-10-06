const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("vayDesktop", { isDesktop: true });
