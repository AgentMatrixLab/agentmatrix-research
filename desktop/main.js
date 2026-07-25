const { app, BrowserWindow, Menu, ipcMain, shell } = require("electron");
const path = require("path");

const DEV_FRONTEND_URL = process.env.FACTOR_LAB_FRONTEND_URL;
const DEFAULT_ZOOM_FACTOR = 0.9;
const MIN_ZOOM_FACTOR = 0.75;
const MAX_ZOOM_FACTOR = 1.2;
const ZOOM_STEP = 0.05;

function clampZoom(value) {
  return Math.min(MAX_ZOOM_FACTOR, Math.max(MIN_ZOOM_FACTOR, value));
}

function frontendIndexPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "frontend", "factor-lab-dashboard", "index.html");
  }
  return path.join(__dirname, "..", "frontend", "factor-lab-dashboard", "index.html");
}

function iconPath() {
  const packagedIcon = path.join(process.resourcesPath, "build", "factor-lab-logo.png");
  const devIcon = path.join(__dirname, "build", "factor-lab-logo.png");
  return app.isPackaged ? packagedIcon : devIcon;
}

function createWindow() {
  const mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1180,
    minHeight: 760,
    title: "Factor Lab",
    icon: iconPath(),
    show: false,
    backgroundColor: "#f5f7fc",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: true,
    },
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  mainWindow.webContents.once("did-finish-load", () => {
    mainWindow.webContents.setZoomFactor(DEFAULT_ZOOM_FACTOR);
  });

  mainWindow.webContents.on("before-input-event", (event, input) => {
    if (!input.control) return;
    const current = mainWindow.webContents.getZoomFactor();
    if (input.key === "+" || input.key === "=") {
      mainWindow.webContents.setZoomFactor(clampZoom(current + ZOOM_STEP));
      event.preventDefault();
    } else if (input.key === "-") {
      mainWindow.webContents.setZoomFactor(clampZoom(current - ZOOM_STEP));
      event.preventDefault();
    } else if (input.key === "0") {
      mainWindow.webContents.setZoomFactor(DEFAULT_ZOOM_FACTOR);
      event.preventDefault();
    }
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });

  if (DEV_FRONTEND_URL) {
    mainWindow.loadURL(DEV_FRONTEND_URL);
  } else {
    mainWindow.loadFile(frontendIndexPath());
  }
}

ipcMain.on("factor-lab:zoom-by", (event, delta) => {
  const webContents = event.sender;
  const current = webContents.getZoomFactor();
  webContents.setZoomFactor(clampZoom(current + delta));
});

ipcMain.on("factor-lab:zoom-reset", (event) => {
  event.sender.setZoomFactor(DEFAULT_ZOOM_FACTOR);
});

app.whenReady().then(() => {
  Menu.setApplicationMenu(null);
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
