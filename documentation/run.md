# Run the QPSO CVRPTW project locally

This repository contains two interfaces for the same route-optimization engine:

- **Next.js dashboard**: the main interactive dark-mode map dashboard.
- **Streamlit application**: the optional legacy/analysis interface.

The Next.js dashboard requires the FastAPI backend to be running. The complete
dashboard therefore uses two terminals: one for FastAPI and one for Next.js.

## 1. Prerequisites

Install the following before starting:

- Python 3.10–3.12
- Node.js 20.9 or newer and npm
- Git, if cloning the repository
- Internet access for the OSM road-network download and map basemap resources

The prototype Stadia branch uses the Stadia dark raster style for the polished
map presentation. Configure its browser-visible key in `vrp-dashboard/.env.local`.
The production OpenStreetMap/vector-fallback workflow remains on the main
development line.

Python 3.11 and Node.js 20 LTS are recommended for the most predictable setup.

## 2. Open the project directory

Open PowerShell, Command Prompt, or a terminal and move to the repository root:

```powershell
cd "D:\Hackathons\SIH 2026\qpso_cvrptw-master (1)\qpso_cvrptw-master"
```

If the repository is stored elsewhere, replace the path with the location of the
folder containing `app.py`, `core`, `tests`, and `vrp-dashboard`.

## 3. Set up the Python backend

### Windows PowerShell

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `python` is not available on Windows, use the Python launcher instead:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The virtual environment must be activated whenever Python commands are run.

## 4. Configure the prototype map and frontend API

Create or edit `vrp-dashboard/.env.local`:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_STADIA_API_KEY=replace_with_your_stadia_maps_key
```

The `NEXT_PUBLIC_` prefix is required because these values are read by the
browser-side dashboard. Never commit the real Stadia key.

After changing `.env.local`, restart the Next.js development server. Never commit
a real API key to source control.

## 5. Start the FastAPI backend

### Optional live TomTom traffic mode

The **Simulated (Seeded)** option is fully local and uses the project's seeded
traffic model. The **Live Traffic API** option sends one server-side Matrix
Routing request to TomTom for the selected depot and delivery stops. The same
live distance and traffic-aware travel-time matrix is then used by QPSO, GA,
and A*; the optimization loop itself makes no additional TomTom requests.

Create a `.env` file in the repository root and keep the key server-side:

```dotenv
TOMTOM_API_KEY=replace_with_your_tomtom_server_key
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# Optional live-traffic cost controls
TOMTOM_LIVE_CACHE_TTL_SECONDS=600
TOMTOM_MIN_REFRESH_SECONDS=60
TOMTOM_MAX_LIVE_REQUESTS_PER_HOUR=5
TOMTOM_MAX_LIVE_REQUESTS_PER_DAY=20
TOMTOM_MONTHLY_TRANSACTION_BUDGET=2000
TOMTOM_MAX_LOCATIONS=100
```

Do **not** put the TomTom key in `vrp-dashboard/.env.local` and do not prefix it
with `NEXT_PUBLIC_`. Next.js exposes `NEXT_PUBLIC_` values to the browser.
TomTom live mode requires a valid Matrix Routing entitlement and is subject to
the limits of the selected TomTom plan. Start with a small number of delivery
stops while testing.

Open **Terminal 1** at the repository root, activate the environment, and run:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn core.api:app --reload --host 127.0.0.1 --port 8000
```

On macOS or Linux, use:

```bash
source .venv/bin/activate
python -m uvicorn core.api:app --reload --host 127.0.0.1 --port 8000
```

The API is available at `http://localhost:8000`, with interactive documentation
at `http://localhost:8000/docs`.

Leave this terminal running. The first optimization for a location may take
longer because the OSM road network has to be downloaded and processed.

## 6. Start the Next.js dashboard

Open **Terminal 2** at the repository root:

```powershell
cd vrp-dashboard
npm ci
npm run dev
```

On later runs, `npm ci` is only needed when dependencies change. You can start
the already-installed frontend with just `npm run dev`.

Open [http://localhost:3000](http://localhost:3000) in the browser.

The normal request flow is:

```text
Browser :3000  ->  FastAPI :8000  ->  OSM/traffic/optimization engine
```

## 7. Optional: run the Streamlit interface

The Streamlit application is separate from the Next.js dashboard and does not
require the FastAPI terminal. Open another terminal at the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501). Do not start Streamlit and
the Next.js dashboard on the same port.

## 8. Verify the installation

From the repository root with the virtual environment active:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q core app.py
```

From `vrp-dashboard`:

```powershell
npm run lint
npx tsc --noEmit
```

The expected result is a passing test suite, no Python compilation errors, and
no TypeScript or ESLint errors.

## 9. First-use checklist

1. Start FastAPI and confirm that `http://localhost:8000/docs` opens.
2. Start Next.js and open `http://localhost:3000`.
3. Confirm that the Stadia dark basemap is visible.
4. Select Salt Lake Sector V or Manhattan.
5. Choose delivery stops, vehicles, capacity, traffic mode, and optimizer settings.
6. Click **Initialize Dispatch Sequence**.
7. Use the algorithm selector to inspect QPSO, GA, or A* routes.

## 10. Troubleshooting

### The browser shows “Failed to reach FastAPI optimization engine”

- Confirm the backend terminal is still running.
- Check that the backend is listening on port `8000`.
- Confirm `NEXT_PUBLIC_API_URL=http://localhost:8000` in `.env.local`.
- Restart Next.js after changing `.env.local`.

### The map background is blank

- Confirm the browser has internet access and that requests to
  `https://tiles.stadiamaps.com` are not blocked.
- Confirm `NEXT_PUBLIC_STADIA_API_KEY` is present and valid.
- Check the browser Network panel for tile requests and the console for mixed
  content or Content Security Policy errors.
- Route overlays are independent of the basemap and may still be generated if
  Stadia tiles are temporarily unavailable.

### Optimization takes a long time

- The first run downloads and processes the selected OSM network.
- Use fewer delivery stops, particles, or iterations while testing.
- Keep the backend terminal open and watch it for the detailed error.
- Avoid sending many simultaneous requests to public OSM services.

### The API returns a capacity or route error

- Increase vehicle capacity or fleet size.
- Reduce the number of delivery stops.
- Confirm that each generated customer demand can fit into the fleet.
- For a custom location, confirm that the OSM place name resolves to a sufficiently large connected road network.

### Live traffic mode returns a TomTom error

- Confirm `TOMTOM_API_KEY` is present in the repository-root `.env` file.
- Make sure the key is active and entitled to Matrix Routing v2.
- Confirm that the selected location count is within the limits of your TomTom plan.
- Check that the backend has outbound HTTPS access.
- Use Simulated (Seeded) mode when testing without a TomTom key or when the provider is unavailable.

When a live request is served from the cache or falls back to the local model,
the response includes a `traffic` object describing the provider, cache status,
fallback reason, and estimated monthly transaction usage.

### PowerShell refuses to activate `.venv`

Run this for the current PowerShell session, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Port 8000 or 3000 is already in use

Stop the process using the port, or use an alternate backend port:

```powershell
python -m uvicorn core.api:app --reload --port 8001
```

If the backend uses port `8001`, update `NEXT_PUBLIC_API_URL` to
`http://localhost:8001` and restart Next.js.

## 11. Stop the project

In each running terminal, press `Ctrl+C`. To leave the Python virtual
environment, run:

```powershell
deactivate
```

The `.venv` directory can be reused for future runs; dependencies do not need to
be installed again unless `requirements.txt` changes.
