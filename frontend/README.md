# EDIM Frontend

This frontend is a static browser app used by the local EDIM backend and by the hosted backend handoff path. It intentionally keeps the runtime boundary simple: the backend serves the same static bundle, and the UI talks to the backend through the browser API client.

## Structure

- `index.html` defines the static shell, global styles, third-party browser libraries, and script load order.
- `api-client.js` owns backend URL selection, local/backend switching, test-user headers, downloads, and low-level HTTP helpers.
- `app.jsx` owns the React application, project workspace, model-run UI, graph workspace, result views, and high-level API methods.
- `hero-visual.jsx` owns the production landing-page hero visualization used by `app.jsx`.
- `hero-defaults.json` contains the static hero visualization settings.
- `methodology/` contains the isolated user-facing methodology page.
- `assets/webp/` contains optimized landing-page image assets used by the hero background.
- `geo/` contains bundled map assets used by the result map.

## Build

```bash
npm run build
```

The build validates the model-owned architecture catalog and writes a static bundle to `frontend/dist/`.

## Backend Switching

The UI can run against:

- `local`: the same origin that served the frontend.
- `backend`: the hosted backend configured through `EDIM_BACKEND_API_BASE`.

`api-client.js` stores the selected mode in local storage and exposes the transport layer as `window.EDIM_HTTP_CLIENT`. `app.jsx` builds the model/workspace-specific `window.EDIM_API_CLIENT` on top of that transport layer.

## Handoff Notes

- UI components should not construct backend URLs directly. Add transport behavior to `api-client.js` or high-level workspace methods to the API-client wrapper in `app.jsx`.
- Keep model-specific graph/layout behavior driven by `model_runtime/edim_model/architecture_catalog.json`.
- Do not commit generated `frontend/dist/` output unless the deployment process explicitly changes to require it.
