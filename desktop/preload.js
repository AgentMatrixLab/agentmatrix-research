const { contextBridge, ipcRenderer } = require("electron");

window.addEventListener(
  "wheel",
  (event) => {
    if (!event.ctrlKey) {
      return;
    }
    event.preventDefault();
    ipcRenderer.send("factor-lab:zoom-by", event.deltaY < 0 ? 0.05 : -0.05);
  },
  { passive: false },
);

contextBridge.exposeInMainWorld("factorLabDesktop", {
  platform: process.platform,
  apiBase: "http://127.0.0.1:8012/api/agents/factor-lab",
  resetZoom: () => ipcRenderer.send("factor-lab:zoom-reset"),
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    node: process.versions.node,
  },
});
