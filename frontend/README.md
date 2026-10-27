# AgriTwin-CPS offline 3D viewer

A local Chinese-language viewer for Python experiment artifacts. Streamlit continues to run and
configure experiments; this frontend renders saved state, devices, trends and evidence. The
black/white interface uses functional labels and keeps scientific provenance available.

Requires Node **22.23.0** (at least 22.12). Dependencies are exact-pinned in `package-lock.json`.

```bash
cd frontend
npm ci
npm run dev -- --port 5173
# Open http://127.0.0.1:5173/
npm test
npm run format:check
npm run build
npm run preview -- --port 4173
```

Click **加载仿真示例** to view the actual bundled synthetic run, or **加载实验文件** and select
`trajectory.csv` plus configuration/metadata/events from one saved run directory. Optional
files are listed under **支持的文件**. No file is uploaded. Use play/pause, step, speed and slider
controls; click a scene marker/device button for details, and an event row to jump to its time.
Only the selected frame drives the scene, cards, inspector and chart cursor. The loading/error/
empty states are functional; failed import preserves the previous run.

The greenhouse includes shared frame/bed geometry, instanced plants, glass, three sensor markers,
a fan and irrigation equipment. Drag to orbit; scroll to zoom. Layout is schematic, without a
spatial temperature field. Actual recorded ventilation drives fan motion; actual irrigation drives
the irrigation indicator. Measurements without simulation truth never gain a truth curve.
Missing data display “暂无数据”. See [data contract](../docs/FRONTEND_DATA.md).

To regenerate the demo using the installed Python package, from the repository root:

```bash
uv sync --frozen --extra dev --extra ui --no-editable --reinstall-package agritwin-cps
.venv/bin/python scripts/export_frontend_demo.py --output results/new_frontend_demo
```

This explicitly replaces the viewer's demo assets from a new preserved run. It does not replace
existing result directories. Source/config hashes accompany the data; source changes require a
new output path. Do not interpret the demo as field validation or select research parameters from it.

Limitations: all files are parsed in memory; no live link, experiment execution, backend server,
spatial calibration, radio model or GPU performance guarantee. The production bundle includes
Three.js and currently triggers Vite's large-chunk advisory. WebGL failure leaves numeric views
usable. Unit/component tests cover parsing, source/time distinctions, load failure, event jumps
and synchronized UI state; actual GPU rendering is checked separately in the browser.
