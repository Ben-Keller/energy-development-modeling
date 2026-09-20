# Frontend implementation workplan

20 September 2026 · Baseline `14a7781` · Status: frontend implemented; backend backlog remains deferred. See the [completion record](frontend-implementation-completion-2026-09-20.md).

Use the [visual review](figma-visual-review-2026-09-20.md), [side-by-side evidence](figma-visual-2026-09-20/index.html), and [original annotation/source review](figma-implementation-review-2026-09-20.md) together. The copied Figma is the visual reference; existing correct analytical behavior and frozen API contracts remain authoritative.

## Scope and backend freeze

Implement frontend presentation, navigation, accessibility, component composition and API-client use of **already-existing contracts only**. Do not modify backend code, schemas, migrations, workers, queue/execution behavior, model calculations, dataset validation rules, authorization, deployment configuration, or response contracts. Do not generate new server-derived values in the browser and present them as authoritative.

A missing API field is a frontend unavailable state or an explicitly deferred request. It must not expand a frontend ticket into backend development. Do not send server-owned fields such as dataset snapshots or execution state in create/patch payloads. Verify request fixtures against the existing public `configuration` shape; legacy fixtures containing internal `request` records must not become a new contract.

The freeze does not block using existing dataset, project, model, comparison, report and export endpoints. Implement and test with fixtures/disposable test records; no production mutations are needed for this workplan.

## Delivery sequence

Each batch is independently reviewable. P1 fixes precede visual polish. Acceptance criteria apply to the implemented batch, not to this planning deliverable.

### FE-01 — Restore readable setup and stable empty states · P1

**Changes:** Move the primary scenario/policy editing form into normal responsive layout, outside the pan/zoom transform; reuse existing state, validators and submission serialization. Present scenario selectors and levers in two columns when space allows and one column on narrow screens. Retain the diagram as a secondary overview with selection/expand controls; avoid duplicate active form controls. Preserve dataset selection, readiness feedback and execution actions. Put the execution panel beside the form on wide layouts and in document flow on mobile.

Fix `RankedBars` referencing undefined `normalizedFilter`; add local filter state in FE-05 or remove the invalid reference immediately. Fix the clipped mobile brand and dialog gutters as targeted layout corrections.

**Acceptance:** At 360, 412, 768, 1280 and 1440px, every setup field and lever value is readable and reachable without horizontal canvas panning. Keyboard tab order reaches all inputs; changing inputs produces the same existing request shape and readiness behavior. Graph interactions still work in the secondary view. Empty results do not throw. Brand and modal bounds stay within the viewport. Vertical document scrolling is allowed; shrinking the whole form to illegible scale is not a solution.

**Touches:** `frontend/app.jsx` setup/graph composition, `RankedBars`, brand/dialog components and their active CSS rules. No backend dependency.

### FE-02 — Shared visual foundations and navigation · P1/P2

**Changes:** Define a small set of surface, border, text, accent, status, spacing and type tokens using the current design system. Resolve Figma component styles before exact color/font matching. Prefer restrained panels, cyan action emphasis and obvious selected tabs; check contrast rather than copying pale colors blindly. Keep official UNDP assets and existing licensed fonts unless the design supplies a justified replacement.

Build consistent page header, panel, field group, button, status badge and dialog styles. Use roughly 640px form dialogs on desktop, constrained by viewport gutters; larger dialogs only for genuinely complex content. Reduce repeated small uppercase labels and unnecessary nested borders. Introduce Projects / Dataset library navigation and hash-based location state using the existing deployment: project/model/result tab deep links, browser Back/Forward and reload recovery. Preserve the methodology route and handle unknown/stale IDs through existing errors.

**Acceptance:** Header and focus indicators remain clear at mobile widths and 200% zoom. Dialogs trap focus, restore the trigger, support Escape and scroll within available height. Navigation is keyboard operable. Reloaded links retain their destination; a missing record shows a useful recovery path. No hosting rewrite or server routing change.

**Dependency:** FE-01 layout corrections. Consolidate only CSS touched by this batch; do not start a wholesale rewrite of all phase styles.

### FE-03 — Dataset library using existing operations · P1

**Changes:** Mount `UploadedDatasetsPanel` as the global Dataset library. Clearly separate user uploads, system-managed sources and project assignment. Show Name, Format, Size, Last updated and Projects using returned metadata; add accessible client-side sorting, search and format filtering. Show unavailable size/date explicitly and distinguish no assignments from unavailable usage metadata.

Expose existing upload/version creation, rename, download, version activation, project assignment and version deletion. Explain the difference between activating a version and assigning one to a project. Reuse server validation messages. Render existing 409 referenced-version protection with actionable context. Do not introduce a whole-dataset delete, detach or undo operation without an existing contract. Make loading, uploading, empty, partial metadata and error states deliberate.

**Acceptance:** A fixture-backed journey opens the library from the portfolio, uploads a version, renames it, assigns a specific version to a project and confirms the displayed assignment. Referenced-version deletion fails visibly without hiding the item; unreferenced deletion refreshes the list. No server request on each sort/filter keystroke. No new file-format promise based solely on mockup badges.

**Dependency:** FE-02 destination/shell. Existing dataset endpoints suffice; richer profiling is deferred under B-01.

### FE-04 — Project and model management · P1

**Changes:** Compact project headers/cards and prioritize status, geography, updated date and available counts over decorative imagery. Retain the current collapsed archive and dedicated comparison journey. Surface active/failed counts where the existing summary supplies them. Use reports/exports counts when the relevant existing project lists are loaded; do not fetch every project's artifacts just to fill portfolio cards.

Add a shared Model actions menu/dialog to cards and model pages. Wire existing rename, duplicate and delete handlers where permitted. Preserve confirmation, queued/running restrictions and existing error handling; do not imply queued jobs can be deleted immediately. Reconcile selection/navigation after deletion and prevent duplicate submissions. Optional tab closing is local UI state, never persisted deletion, and must protect unsaved edits.

Improve comparison selection feedback, reference visibility and table readability. Preserve the seven metric families, deltas and successful-run eligibility. Provide a report action from comparison only if the existing report handler can truthfully represent the selected scope; otherwise link to project Reports without calling a project-wide report a selected-model report.

**Acceptance:** Draft and completed model actions are reachable without a discarded sidebar. Confirmation names the target model and current deletion consequences. Cancel is harmless; errors preserve context. Ineligible models explain why comparison is disabled. On narrow screens the matrix has sticky row labels and an obvious horizontal-scroll affordance. Missing counts are not fabricated as zero.

**Dependency:** FE-02 shared controls; no new model lifecycle or reporting contracts.

### FE-05 — Results, evidence and reusable widgets · P1/P2

**Changes:** Replace the dense inline configuration block with a compact summary and expandable, read-only Inputs section. Render the existing public configuration: architecture, engine, scenario, target, year, execution profile and levers. Lazily retrieve immutable dataset provenance from the existing authorized diagnostics endpoint only where its frozen deployed contract is available. Render an allowlist of human-readable fields, not a raw internal record. If unavailable, show that limitation without replacing historic values with current settings. No edit affordance on a completed snapshot.

Move management into the shared dialog, retain downloads, and keep the four correctly named result tabs. Always show the evidence state, including Exploratory only and Not evaluated, with a short explanation; expandable detail must not hide material limitations. Do not infer a stronger assurance level from a successful execution.

Create reusable metric, chart, map, quality and diagnostic cards with content-driven responsive sizing. Distinguish whole-run totals from selected geography. Restore chart-local label search, retain Top N, apply filtering before limiting, expose matching/total counts, preserve signed values and units, and differentiate no data from no matches. Show unavailable metrics explicitly rather than creating zeroes. Preserve all current analytical panels and map behavior.

**Acceptance:** Completed configuration remains accessible without crowding results. Snapshot data does not change when the current library version changes. Diagnostics failure leaves results usable. Evidence limitations are visible before opening Technical details. Charts handle empty, filtered-empty, long-label, negative and large datasets without errors; controls affect only their own chart. Map selection and global results have unambiguous labels.

**Dependencies:** FE-02 and FE-04. Missing provenance support follows B-02; it does not block the configuration summary or other results work.

### FE-06 — Artifact history and final verification · P2

**Changes:** Replace the unconditional first-six report/export truncation with View all or client-side paging of the returned records. Preserve download, provenance and evidence metadata. Avoid claiming completeness beyond the existing endpoint's returned history. Remove superseded CSS only where the new components replace it; keep style ownership explicit rather than adding another broad override layer.

**Acceptance:** A fixture with more than six reports/exports makes every returned item reachable; empty/error states work. Shared components do not regress methodology, graph navigation, advanced comparison or archive behavior. Final screenshots are reviewed at all five target widths and snapshot baselines are updated only for intended changes.

**Dependency:** Earlier batches. Server pagination/retention improvements remain B-03.

## Existing contracts versus deferred work

| Need | Frontend implementation now | Boundary |
| --- | --- | --- |
| Dataset management | Existing list/create/update/upload/version/download/activate/project-assignment/version-delete APIs | No new validation, detach, full-entity deletion or transactional behavior |
| Model actions | Existing project-run patch/duplicate/delete and current execution controls | Preserve active-run restrictions and deletion semantics |
| Completed inputs | Public run `configuration`; existing diagnostics record for permitted provenance | No public schema expansion; graceful unavailable state if diagnostics is absent |
| Evidence | Render returned status, summary and diagnostic values accurately | No recalculation of scores, confidence or evidence classification |
| Counts | Existing model/completed/active/failed summary fields; already-loaded artifact lists | No new portfolio aggregates or costly eager per-project fan-out |
| Comparison/reporting | Existing selection, comparison metrics and project report/export flows | No new selected-run report contract assumed |
| Search/navigation/history | Client filtering/sorting, hash navigation, display of returned records | No server search, routing, pagination or retention changes |

Contract references inspected read-only: `backend/api_service/schemas.py` (`ProjectRunListItem`, `PublicRunConfiguration`, `ProjectVisualSummary`, `InputDatasetDescriptor`); `backend/api_service/api/routers/datasets.py`; `backend/api_service/api/routers/runs.py`. Verify against the deployed frozen version before wiring optional diagnostics behavior. This is contract consumption, not authorization to modify those files.

## Deferred backend backlog — do not start during the freeze

These are grouped follow-up candidates, not dependencies silently included in frontend batches. Open them only after an explicit unfreeze and separate scope agreement.

| Group | Deferred requests | Frontend fallback during freeze |
| --- | --- | --- |
| B-01 Dataset metadata and lifecycle | Authoritative row counts, schema profiles, richer quality summaries; additional formats/validation; atomic upload improvements; detach, whole-dataset deletion or undo if required | Display returned size/usage/version metadata, existing validation and protected version deletion; omit unsupported actions |
| B-02 Stable provenance contract | A dedicated public immutable input/dataset snapshot if the existing diagnostics endpoint is unavailable or unsuitable; additional execution provenance not currently exposed | Public configuration plus available authorized snapshot fields; label unavailable provenance explicitly |
| B-03 Aggregation and scale | Portfolio report/export aggregates, complete cross-project usage if absent, server-side filtering/pagination and guaranteed full artifact history | Existing summary counts and loaded lists only; client-side sort/filter/page; no invented totals or eager N+1 portfolio requests |
| B-04 Analytical/reporting semantics | New evidence calculations, uncertainty methods, geographic outputs, metric definitions, selected-run report semantics, model/runtime changes | Render current values/limitations faithfully; retain current report scope and supported comparisons |

None of these groups should advance backend implementation, migrations, API negotiation or deployments as part of the frontend work.

## Verification and handoff

Use deterministic API mocks reflecting the existing public response shapes. Add focused tests for previously missed failures: form/control bounds, empty charts, reachable library/actions, protected deletion, visible evidence, immutable snapshot fallback, deep-link recovery and more-than-six artifact records. Include loading, network failure, 409 conflicts, missing metadata, queued/running and completed states. Verify keyboard focus, dialog behavior, meaningful labels, contrast and touch targets alongside screenshots.

Run the frontend build and appropriate existing desktop/mobile UI suites after each meaningful batch; run the full suite at integration. The existing baseline has three snapshot failures across 36 tests; inspect these before replacement rather than accepting them wholesale. No backend tests or backend services need to be changed to ship presentation work. If contract verification uncovers a genuine blocker, record it in B-01–B-04 and ship the documented fallback.

Implementation handoff order: **FE-01 → FE-02 → FE-03 → FE-04 → FE-05 → FE-06**. A frontend-only diff, reviewed screenshots and passing relevant functional checks are required before considering each batch complete. The six frontend batches have been implemented. The completion record documents verification and limitations; B-01–B-04 remain deferred.
