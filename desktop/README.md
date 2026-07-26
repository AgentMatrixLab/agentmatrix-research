# Factor Lab Desktop

Electron desktop shell for the existing Factor Lab frontend.

## Scope

This app only wraps the existing static frontend in `frontend/factor-lab-dashboard`.
It does not start Python, run agents, fetch market data, or compute factors.

The current frontend still reads the local Flask API:

```text
http://127.0.0.1:8012/api/agents/factor-lab
```

Start Flask separately before opening the desktop app:

```powershell
cd <repo-root>
.\.venv\Scripts\python.exe backend\factor_lab_api.py
```

## Install desktop dependencies

```powershell
cd <repo-root>\desktop
npm install
```

## Development

```powershell
npm run dev
```

By default this loads:

```text
../frontend/factor-lab-dashboard/index.html
```

If you run a frontend static server, you can point Electron to it:

```powershell
$env:FACTOR_LAB_FRONTEND_URL="http://127.0.0.1:5173"
npm run dev
```

## Build Windows app

```powershell
npm run build
```

Outputs are written to:

```text
desktop/dist
```

The build configuration targets:

- Windows NSIS installer
- Windows portable executable

## macOS note

The same Electron code can build a macOS `.dmg`, but macOS distribution usually
needs a Mac machine for reliable packaging, code signing, notarization, and Gatekeeper
compatibility.

```bash
npm run build:mac
```

## Security boundary

- `nodeIntegration` is disabled.
- `contextIsolation` is enabled.
- Renderer code does not access Node.js or `fs` directly.
- The preload script only exposes metadata for now.
