# Frontend workplan implementation

20 September 2026 · Implements FE-01 through FE-06 from the [approved workplan](frontend-implementation-workplan-2026-09-20.md), incorporating the hierarchy review and Figma visual checks.

[View the implemented frontend gallery](frontend-implemented-2026-09-20/index.html).

## Delivered

| Batch | Result |
| --- | --- |
| FE-01 Setup and empty states | Scenario selectors and policy levers now live in a responsive form outside the pan canvas. The model flow and dataset inspector are secondary and mount on first opening. Empty charts no longer reference an undefined variable. Header clipping and dialog gutters are corrected. |
| FE-02 Foundations and navigation | Shared charcoal surfaces, cyan actions, readable fields, visible focus and responsive header/dialog rules reuse the current components and UNDP assets. Dialogs render outside card containers to avoid inherited card layout constraints. Projects / Dataset library navigation and project/model/result-section hash links support reload, Back/Forward, methodology and unavailable-record recovery. |
| FE-03 Dataset library | The existing library is mounted. Name, format, size, updated date and project usage are visible; client sorting/filtering works on desktop and mobile. Upload/create, additional versions, rename, activation, assignment, download and protected version deletion use existing APIs. Failed version-list reads preserve other results. Retrying a failed initial upload can reuse the already-created dataset. Unknown metadata is labeled explicitly. |
| FE-04 Projects and models | A shared Model actions dialog provides rename, duplicate and confirmed deletion on cards, setup and results. Active executions retain deletion restrictions. Portfolio status counts expose existing active/failed fields. The collapsed archive and advanced comparison remain intact; comparison retains reference selection, seven output families and deltas, adds a scroll hint and existing selected-model reporting action. |
| FE-05 Results | Completed configuration is expandable and read-only, rendered from the selected model record. Dataset provenance is fetched lazily from the existing diagnostics endpoint with an unavailable fallback and an allowlist of display fields. Evidence states and execution warnings remain visible. Charts have local search, matching counts and Top N; missing numeric values display as unavailable rather than zero. Existing metric, map and diagnostic components remain in use. |
| FE-06 History and verification | All records returned by report/export endpoints are reachable, replacing first-six truncation. Failed artifact-history reads show unavailable states. Obsolete inline-input/action CSS was removed from the existing stylesheets, with shared component styles maintained in `platform-components.css`. |

Optional session-only tab closing was not introduced: the existing model navigation remains available, and closing a tab is never treated as deletion.

## Verification

**Final result: frontend build passed; 54/54 browser tests passed in the final run (45.1 seconds), without updating snapshots.** `git diff --check` passed.

The frontend build and browser checks run against deterministic mocked APIs using the frozen public configuration response shape. No live backend execution, upload, deletion or deployment was performed.

The suite covers existing analytical and navigation behavior plus new tests for:

- Setup control bounds at 360, 412, 768, 1280 and 1440px; saving only the permitted public configuration fields.
- Deep-link reloads, browser history, result-section restoration and unavailable projects.
- Model rename/duplicate, cancelled deletion and active-run protection.
- Lazy immutable dataset provenance, visible evidence and unavailable diagnostics.
- Empty and filtered-empty charts with independent local controls.
- Dataset sorting, assignment, protected deletion, creation, additional upload versions, rename and successful deletion.
- All nine returned report/export records remaining accessible in a history fixture.
- Dialog gutters, keyboard focus and return to the originating control; existing and library accessibility checks.

Screenshots were inspected for setup, header, model cards/actions, datasets, result inputs/evidence, comparison and charts. Updated baselines reflect intentional layout and visibility changes. The gallery uses fixtures; it does not establish production data completeness or exact prototype parity.

## Backend freeze and remaining boundaries

No files under `backend/`, `model_runtime/` or repository-level `scripts/` were modified. No API schema, database migration, validation rule, worker, model computation, authorization or deployment change was made.

B-01 through B-04 remain deferred: richer dataset profiling/lifecycle contracts, a dedicated public provenance contract if required, server aggregation/pagination, and new analytical/reporting semantics. Optional diagnostics failure does not block results. Artifact lists show what the existing service returns; the frontend does not claim to retrieve server history beyond that contract.

Exact Figma variable bindings, prototype animation behavior and production backend integration are not asserted by this frontend review. The implemented layout follows the reviewed design intent while retaining existing analytical functionality.
