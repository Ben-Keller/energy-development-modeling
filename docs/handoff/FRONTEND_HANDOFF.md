# Frontend handoff

Updated 21 September 2026. This is the current UI delivery summary; backend integration contracts remain in [BACKEND_HANDOFF.md](BACKEND_HANDOFF.md). Build and test commands are in the [frontend README](../../frontend/README.md).

## Delivered behavior

- One persistent header across landing, projects, models, dataset library, and methodology; hash routes support reloads and browser history without hosting rewrites.
- Your Projects portfolio with dataset library access below the projects and in the user menu.
- Project workspace with metadata and four totals above the Models area; model creation and comparison in the model toolbar; activity, reports, and exports together in a responsive right panel.
- Readable setup forms outside the graph transform, with the graph retained as a secondary overview.
- Shared model management actions, clear Open and Export actions, and existing lifecycle restrictions.
- Dataset search, sort, upload/version management, assignment, and protected deletion through existing endpoints.
- Results with read-only recorded inputs, compact evidence/limitations disclosures, local chart filtering, and access to every report/export returned by the service. Successful execution does not imply validated evidence.
- Responsive spacing, accessible controls, and correctly resolved static assets under the `/ui/` mount.

## Integration boundary

These frontend changes require no new backend endpoints, schema migrations, model calculations, or deployment configuration. Preserve the existing API-client transport, runtime target selection, compatibility manifest checks, and descriptor-based downloads. Normal static frontend rebuild/deployment is required.

Backend development remains frozen for this UI work. After the backend deployment is stable, verify the frontend against the hosted service separately; mocked browser tests do not establish production integration. Optional provenance failures leave results available, and the UI only presents metadata and history returned by the current service.

## Deferred backend candidates

These are optional follow-up scopes, not prerequisites for shipping the frontend. Agree scope after the backend is stable; they are not all configuration-only or necessarily small changes.

| Group | Potential work | Current frontend behavior |
| --- | --- | --- |
| B-01 Dataset metadata and lifecycle | Authoritative row counts/schema profiles/quality summaries; more formats and validation; atomic uploads; detach, whole-dataset deletion or undo if needed | Uses returned metadata, current validation, assignment and protected version deletion; unsupported actions are omitted |
| B-02 Public provenance | Dedicated immutable input/dataset snapshot contract if authorized diagnostics are insufficient; additional execution provenance | Shows public configuration and available snapshot fields, with unavailable provenance stated explicitly |
| B-03 Aggregation and scale | Portfolio report/export totals, complete cross-project dataset usage, server filtering/pagination and guaranteed full history | Uses existing summaries and loaded lists with local filtering; does not invent totals or claim complete server history |
| B-04 Analytical/reporting semantics | New evidence/uncertainty calculations, geographic outputs, metrics, selected-model report scope, or model-runtime changes | Preserves current calculations, limitations, report scope and supported comparisons |

## Verification and maintenance

`frontend/tests/ui.spec.js` holds UI and screenshot regressions. `frontend/tests/workspace-flows.spec.js` covers responsive forms, public request shapes, routing, dataset operations, model actions, evidence fallbacks, artifact history, and persistent-header behavior using deterministic API mocks.

Keep assertion baselines in `frontend/tests/ui.spec.js-snapshots/`. Generated inspection screenshots and traces belong in ignored `frontend/test-results/`, not documentation. The dated Figma reviews, intermediate galleries and completed workplan have been retired; this note preserves their delivery status and backend follow-ups.

Design reference: [shared Figma copy](https://www.figma.com/design/Mt8Gg5L0MoY0tZsvPFfR4t/UNDP-Energy-Modeling-Platform-Shared-16-06-2026--Copy-). The implemented behavior includes subsequent product refinements and is not an exact copy of every visual detail.
