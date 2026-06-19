# React Frontend

This is the new React/Vite frontend for Arya tech Repo Quality Platform.

The old FastAPI/Jinja frontend remains intact at `/`. This React app starts by replacing only the Pipeline Monitor experience and consumes the existing backend APIs.

## Development

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173/react/`.

Vite proxies `/api/*` requests to `http://127.0.0.1:8000`, so keep `python server.py` running in another terminal.

## Production Build

```powershell
cd frontend
npm run build
```

FastAPI serves the built app from `/react` when `frontend/dist/index.html` exists.
