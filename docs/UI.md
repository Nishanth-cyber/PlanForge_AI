# PlanForge AI — Web UI Architecture & Guide

Phase 14 delivers a modern, research-grade Web User Interface for **PlanForge AI**, providing complete visual interaction, inspection, verification, and an interactive 2D irregular plot editor across the multi-agent generative architecture.

---

## 1. Architectural Principles & Invariants

1. **Zero Generation Logic in Frontend:**
   - The web UI is strictly a presentation and interaction layer.
   - All space allocation (ASAA), constraint solving, geometry construction, staircase placement, independent validation, agentic refinement, and multi-design diversity remain 100% authoritative on the FastAPI backend.

2. **Direct Vector Geometry Consumption:**
   - SVG rendering operates directly on backend-computed floating-point coordinate geometries (`GeoRoom`, `GeoWall`, `GeoDoor`, `GeoWindow`, `GeoStaircase`).
   - Door swing arcs, wall thicknesses, window cutouts, stair flight treads, and room bounding polygons are drawn using true dimensional data from the `FloorPlan` schema.

3. **Neutral Scientific Presentation:**
   - Multi-design alternatives are compared factually across objective metrics (gross area, room count, circulation efficiency, constraint compliance).
   - No subjective "winner", "recommended", or artificial quality scores are fabricated.

4. **Real-World Coordinate Invariant:**
   - Coordinates are always created, edited, and transmitted in **meters** `(x, y)` relative to `(0, 0)`.
   - The interactive canvas maps real-world meter coordinates to screen pixels dynamically. Screen pixels are never sent to the backend.
   - Irregular polygons are never forced into rectangular approximations or bounding boxes.

5. **Transparent Pipeline Progress:**
   - Real-time execution status tracks actual backend agent milestones (Requirements -> Planning -> ASAA -> Architectural LLM -> Geometry -> Validation -> Refinement -> Diversity -> Explainability -> Export).

---

## 2. Technology Stack

- **Framework:** React 19 (`react`, `react-dom`) with TypeScript.
- **Build Tool:** Vite (`vite`, `@vitejs/plugin-react`).
- **Styling:** Custom architectural studio CSS design system (Vanilla CSS with CSS custom properties, dark mode, high contrast, clean typography via Inter and JetBrains Mono).
- **Icons:** Lucid architectural SVG iconography.
- **Testing:** Vitest + React Testing Library + `@testing-library/jest-dom` + `jsdom`.

---

## 3. Directory Structure

```
frontend/
├── dist/                          # Compiled production assets (served by FastAPI)
├── index.html                     # Main HTML template with Google Fonts & SVG favicon
├── package.json                   # Dependencies and scripts
├── tsconfig.json                  # TypeScript configuration
├── vite.config.ts                 # Vite config with backend proxy and Vitest setup
└── src/
    ├── api/
    │   ├── types.ts               # Domain TypeScript interfaces mirrored from Pydantic schemas
    │   ├── client.ts              # Fetch-based HTTP client with typed error handling
    │   └── projects.ts            # API service calls (projects, generate, health, export)
    ├── utils/
    │   └── geometry.ts            # Shoelace formula area, self-intersection check, presets, grid snapping
    ├── components/
    │   ├── layout/
    │   │   ├── Header.tsx         # Top bar with backend health ping, theme toggle & navigation
    │   │   └── TabNav.tsx         # Sub-navigation bar across all 9 research views (including Plot tab)
    │   ├── plot-editor/
    │   │   └── PlotEditor.tsx     # Interactive 2D plot editor (Rectangle vs Irregular Polygon, SVG canvas, vertex table)
    │   ├── floorplan/
    │   │   ├── FloorPlanCanvas.tsx # Interactive 2D vector SVG viewer (pan/zoom, doors, walls, stairs)
    │   │   ├── FloorTabs.tsx      # Multi-floor selection tab bar
    │   │   └── RoomInspector.tsx  # Drawer for inspecting selected room attributes and door links
    │   └── views/
    │       ├── DashboardView.tsx       # Project list, status badges & benchmark presets
    │       ├── NewProjectView.tsx      # 7-Step Architectural Wizard + Benchmark preset loader
    │       ├── ProjectOverviewView.tsx # Pipeline status, execution metrics & agent stage timeline
    │       ├── RequirementsView.tsx    # Parsed architectural program specifications per floor
    │       ├── PlotView.tsx            # Authoritative plot boundary visualizer & coordinates table
    │       ├── AlternativesView.tsx    # Multi-design alternative cards & factual comparison matrix
    │       ├── ValidationView.tsx      # 18-category independent validator report with error drilldown
    │       ├── ExplainabilityView.tsx  # Chronological decision trace & room entity lifecycle explorer
    │       ├── RefinementView.tsx      # Iterative refinement convergence & change log
    │       └── ExportView.tsx          # Export download center for PNG, SVG, JSON, and ZIP bundles
    ├── styles/
    │   ├── index.css              # Theme tokens, resets, typography, and utility classes
    │   └── components.css         # Component styling for canvas, inspector, tabs, tables, and views
    ├── __tests__/
    │   ├── app_render.test.tsx    # App rendering & dashboard navigation tests
    │   ├── floorplan_canvas.test.tsx # SVG vector canvas rendering tests
    │   ├── validation_and_alternatives.test.tsx # Validation, alternatives, and export view tests
    │   ├── plot_editor.test.tsx   # Geometry utilities and PlotEditor component tests
    │   ├── new_project_workflow.test.tsx # 7-step wizard and irregular plot submission tests
    │   └── plot_view.test.tsx     # Authoritative PlotView component tests
    ├── App.tsx                    # Master state coordinator & view router
    └── main.tsx                   # React entry point
```

---

## 4. API Endpoints Consumed

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Check backend service health, version, and LLM provider |
| `/projects` | GET | List all active and persisted benchmark/evaluation projects |
| `/generate` | POST | Trigger full 10-stage agentic generation pipeline (supports `plot_shape`) |
| `/projects/{id}` | GET | Get project status and top-level summary |
| `/projects/{id}/data` | GET | Fetch complete structured project JSON (floor plans, validation, trace, refinement) |
| `/projects/{id}/status` | GET | Poll pipeline execution progress |
| `/projects/{id}/export` | GET | List export artifacts or retrieve file manifest |
| `/projects/{id}/export/bundle` | GET | Download complete ZIP export bundle |
| `/projects/{id}/export/{floor_id}/png` | GET | Download 300 DPI publication-grade raster PNG |
| `/projects/{id}/export/{floor_id}/svg` | GET | Download scalable vector graphic for CAD/BIM import |

---

## 5. Key Interactive Features

### 5.1 Interactive 2D Irregular Plot Editor (`PlotEditor.tsx`)
- **Dual Modes:**
  - **Rectangle Mode:** Inputs for width, length, unit (m or ft), front/rear/side setbacks, orientation.
  - **Irregular Polygon Mode:** SVG-based interactive vector canvas with coordinate axes and grid.
- **Direct Canvas Manipulation:**
  - Click empty canvas to append vertex (snapped to 0.5m grid).
  - Drag existing vertices with live real-time coordinate updates.
  - Click vertex to inspect / delete.
  - Click start point P0 or "Close Polygon" button to seal the boundary.
  - Undo and redo history stack.
- **Synchronized Vertex Table:**
  - Direct numeric editing of X (m) and Y (m) coordinates for every vertex.
  - Editing the table immediately moves vertices on the canvas; dragging on the canvas immediately updates table values.
- **Real-Time Validation & Safety:**
  - Gross area calculated via Shoelace formula in $\text{m}^2$ and sq ft.
  - Continuous non-adjacent edge crossing detection highlights self-intersections in red and blocks pipeline dispatch.
- **Preset Shapes:**
  - Standard Suburban (15m × 25m)
  - L-Shaped Corner (300 m²)
  - Cul-de-sac Trapezoid (320 m²)
  - 5-Sided Urban Infill (235.5 m²)

### 5.2 7-Step New Project Wizard (`NewProjectView.tsx`)
- **Step 1 — Project Info:** Project name, context notes, alternatives (1–4), refinement toggle, max refinement passes, benchmark case loader.
- **Step 2 — Plot Boundary:** Embedded interactive 2D Plot Editor with live validation and setback controls.
- **Step 3 — Floors:** Story count selector (1–3 floors), floor labeling, vertical circulation indicators.
- **Step 4 — Rooms:** Per-floor room schedule manager with preset buttons (+ Bedroom, + Bathroom, + Living), target areas, and counts.
- **Step 5 — Relationships:** Spatial adjacencies, acoustic separations, and front facade orientation intent.
- **Step 6 — Review & Brief:** Comprehensive summary cards and bidirectional natural-language architectural brief preview.
- **Step 7 — Generate:** Final review and dispatch to PlanForge AI orchestrator.

### 5.3 Authoritative Plot Tab (`PlotView.tsx`)
- Dedicated project tab displaying the backend-generated plot polygon, buildable boundary offset, municipal setbacks, and meter coordinates table.

### 5.4 Interactive 2D Vector SVG Viewer (`FloorPlanCanvas.tsx`)
- **Vector Fidelity:** Draws perimeter/interior walls with proper stroke thickness, windows with mullions, doors with 90° swing arcs, and staircases with tread count.
- **Room Inspection:** Hover highlighting and click selection trigger the **Room Inspector Drawer**, displaying gross dimensions, daylight access, room type, aspect ratio, door connectivity, and validation warnings.
- **Pan & Zoom Controls:** Interactive zooming, centering, and reset view.
- **High-Res Toggle:** Instant toggle between interactive SVG mode and high-resolution 300 DPI publication raster rendering.

### 5.5 Minimalist Black & White Theme (Light / Dark)
- Seamless theme toggle between "Light" (architectural paper white mode with sharp black CAD ink) and "Dark" (deep obsidian studio mode).

---

## 6. How to Run & Build

### Development Mode

1. **Start the FastAPI backend:**
   ```powershell
   python -m uvicorn app.api.app:app --host 127.0.0.1 --port 8000 --reload
   ```

2. **Start the Vite development server:**
   ```powershell
   cd frontend
   npm install
   npm run dev
   ```
   The development server runs at `http://localhost:5173/` and proxies all API requests to `http://localhost:8000`.

### Production Build & Static Serving

1. **Build the frontend bundle:**
   ```powershell
   cd frontend
   npm run build
   ```
   This generates optimized static files in `frontend/dist/`.

2. **Run the backend server:**
   ```powershell
   python -m uvicorn app.api.app:app --host 0.0.0.0 --port 8000
   ```
   FastAPI automatically detects `frontend/dist` and serves the Web UI at `http://localhost:8000/`.

### Running Tests

```powershell
# Frontend tests (19 tests across 6 suites)
cd frontend
npm test

# Backend test suite (444 tests)
python -m pytest -q
```
