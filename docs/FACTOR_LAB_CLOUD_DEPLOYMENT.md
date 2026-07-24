# Factor Lab Cloud Deployment

GitHub Pages hosts only the static dashboard. Flask and Quant API access must run on a separate backend service.

## Architecture

- Frontend: GitHub Pages, serving `frontend/factor-lab-dashboard`.
- Backend: Flask app from `backend/factor_lab_api.py`, deployed to Render or another Python host.
- Quant API token: stored as a backend environment variable. Do not put it in frontend code.

## Deploy Flask on Render

1. Push this branch to GitHub.
2. In Render, create a new Blueprint from this repository.
3. Render will read `render.yaml` and create `factor-lab-api`.
4. Set the secret environment variable:

```text
FACTOR_LAB_QUANT_API_TOKEN=<your token>
```

5. Deploy. The backend URL will look like:

```text
https://factor-lab-api.onrender.com
```

## Connect GitHub Pages to Flask

Open:

```text
frontend/factor-lab-dashboard/config.js
```

Set:

```js
window.FACTOR_LAB_API_HOST = "https://factor-lab-api.onrender.com";
```

Commit and push. The GitHub Pages dashboard will then call:

```text
https://factor-lab-api.onrender.com/api/agents/factor-lab
```

For quick testing without changing `config.js`, open the dashboard with:

```text
https://miao050805-arch.github.io/agentmatrix-research/?api=https://factor-lab-api.onrender.com
```

The URL parameter is saved in browser local storage.

## Local Development

When no cloud API is configured, local development still uses:

```text
http://127.0.0.1:8012/api/agents/factor-lab
```

Run locally with:

```powershell
python backend/factor_lab_api.py
```

## Security Notes

- Keep `FACTOR_LAB_QUANT_API_TOKEN` only in the backend host environment.
- Do not commit `.env`, tokens, runtime cache, or factor result files.
- GitHub Pages cannot safely hold private API tokens.
