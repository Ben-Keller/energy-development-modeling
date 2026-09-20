# Visual review: Figma versus the current frontend

Reviewed 20 September 2026 against local commit `14a7781`. The copied Pro file is accessible. This follow-up resolves the screenshot-access limitation in the [earlier implementation review](figma-implementation-review-2026-09-20.md). No application, backend, or Figma changes were made.

**Deliverables:** [Frontend implementation workplan](frontend-implementation-workplan-2026-09-20.md) · [Side-by-side visual evidence](figma-visual-2026-09-20/index.html).

## Coverage

Visually inspected all 11 UI 1 screen frames, the nine-widget section, overview images of both suggestions sections, and four enlarged proposal slides covering setup, results navigation, and model management. The earlier pass read the complete metadata trees and annotations for all 22 suggestion slides. The section overviews are not substitutes for individual full-resolution inspection of every slide.

Captured and inspected eight current frontend states at each of 1280×900 desktop and 412×915 mobile: portfolio, create project, project, new model, setup, comparison, results overview, and energy results. These use the existing frontend's mocked API fixtures, not live production records. Two capture journeys passed; their success means the screens were reached and captured, not that visual defects are absent. No production or frozen backend was contacted by those journeys.

Screenshots establish composition, visible copy, hierarchy, clipping, and component appearance. Exact Figma variable values, font bindings, interactive prototype behavior, and every hover/focus variant were not audited. No mobile Figma frames were supplied; mobile recommendations derive from the implementation's observed behavior. Missing map values and inconsistent fixture counts are not treated as production defects.

## Findings and decisions

| Area | Figma intent and observed implementation | Frontend decision |
| --- | --- | --- |
| Setup | The design exposes scenario selectors and policy levers in a readable two-column input card. The current 1,100px scenario node is wider than its canvas at both tested widths. | Highest priority: make the primary editing form responsive and usable without canvas panning. Keep the graph as a secondary model overview. |
| Mobile header | Current branding starts outside the viewport; title wraps to three lines and controls occupy a separate uneven row. | Reflow the header with an intact UNDP mark, readable title and aligned account/runtime controls. |
| Foundations | Figma has charcoal/olive surfaces, cyan primary actions, light selected tabs, restrained borders and larger labels. Current UI mixes blue gradients, tiny uppercase labels and multiple nested panels. | Establish a small shared palette, spacing and type hierarchy; retain the existing official brand assets and readable semantic states. Resolve exact tokens during implementation rather than guessing from screenshots. |
| Portfolio | Figma has compact operational cards and an archive toggle; implementation has large decorative identities and a separate collapsed archive. | Reduce decoration/hero height where it displaces useful information; retain the collapsed archive, clear project identities, search and existing hierarchy. |
| Dataset library | Figma shows Name, Format, Size, Last Updated and Projects, sortable headers, assignment and row actions. The implementation has a capable library component but no mounted destination. | Restore Projects / Dataset library navigation, mount the component and make existing metadata visible. Implement honest missing-value states. |
| Create dialogs | Figma uses approximately 640px centered forms with clear labels and a predictable footer. Current desktop dialogs are broader and denser; mobile captures show asymmetric side gutters. | Use shared responsive dialog sizing, readable fields and reliable scrolling, with consistent Cancel / primary actions and preserved focus handling. |
| Project/models | Figma prioritizes model status, counts and comparison selection. Current implementation already separates projects and models and provides a dedicated comparison view. | Keep that hierarchy; provide consistent model actions, available status counts and compact metadata. Do not add decorative tabs merely for fidelity. |
| Completed inputs | Figma collapses completed inputs and moves management to a dialog. Current results show six inline configuration fields plus several controls, but no complete accessible input snapshot. | Collapsible, read-only Inputs section plus a Model actions dialog. Show configuration and available immutable provenance, not today's active dataset as historic provenance. |
| Overview/evidence | Figma visibly includes an Exploratory Only badge, data quality, uncertainty and diagnostics. Current evidence component suppresses exploratory/not-evaluated badges; important warnings can be hidden. | Keep a compact evidence/status summary visible. Detailed diagnostics may collapse; uncertainty and missing evaluation must remain explicit. |
| Results/map | Figma distinguishes global and geographic results but labels one global panel ambiguously. Current implementation places maps and global metrics differently. | Preserve clear global versus selected-geography semantics. Do not move panels solely to copy an ambiguous label. Use explicit no-selection, unavailable and loading states. |
| Energy charts/widgets | Figma shows a filter and Top 20, rounded bars, aligned values and several widget sizes. Current chart-local limits are useful, but search is absent and empty charts reference undefined `normalizedFilter`. | Restore local label search, fix the empty branch, add units/context and use reusable responsive cards. Keep chart-local controls and content-driven heights. |
| Comparison | Current advanced comparison has seven metric families, reference selection and deltas beyond the Figma table. The mobile matrix is dense. | Preserve analytical features; improve text, sticky row labels, column navigation and reference visibility. Keep successful-run eligibility. |
| Reports/exports | Current lists stop after six entries with no continuation. | Add a complete view of records returned by existing endpoints, with client-side paging where useful. Do not imply unavailable server history has been fetched. |

### Measured setup and header defects

After fonts and rendering settled, the setup node measured **1,100px wide** in both layouts. At desktop it spans x=−95 to 1005 inside a canvas spanning x=17 to 893 (876px). At mobile it spans x=−344 to 756 inside x=13 to 399 (386px); primary selects span x=−332 to 744. Their labels and numeric lever inputs are outside the initial visible region. This is not just a small screenshot offset or a request for additional zoom controls.

The mobile brand container begins at **x=−33px**, consistent with the visibly clipped logo. Raw [desktop geometry](figma-visual-2026-09-20/current-desktop-geometry.json) and [mobile geometry](figma-visual-2026-09-20/current-mobile-geometry.json) are retained with the evidence.

### Mockup inconsistencies to correct, not reproduce

- UI 1 duplicates the Development results tab; retain Overview / Energy system / Development / Method.
- A comparison selection screen checks a draft despite completed-run comparison semantics. Preserve eligibility checks and make the disabled reason clear.
- Sample counts do not always match visible cards. Derive counts from available authoritative data; unknown is not zero.
- Target year “230”, “Run Naem”, placeholder instructions and the run-profile/engine mismatch are sample errors, not desired product copy.
- A layer named “Language Switcher” visually displays COUNTRY OFFICER. This is not evidence for adding localization or new role switching.
- A tab's close X should never silently delete a persisted model. If tab closing is introduced, it is session navigation with draft protection.
- Dataset screenshots show energy-specific sample names; raw component text-layer names from metadata are not the final displayed copy. Sample filenames are not required datasets or new supported upload formats.

## Evidence and limitations

The gallery links each of the 11 UI frames to the closest current screen, including states with no current counterpart. It also includes widgets, annotated proposals and mobile captures. Source: [copied Figma file](https://www.figma.com/design/Mt8Gg5L0MoY0tZsvPFfR4t?node-id=746-459). Local filenames encode source node IDs. There are 18 Figma PNGs and 16 implementation PNGs.

The earlier full UI suites passed 16/18 desktop and 17/18 mobile tests, with graph-toolbar/portfolio snapshot mismatches; the build passed. Those baseline mismatches remain unresolved because this is a review-only task. The fresh two-test capture run passed but does not supersede the broader suite. The implementation plan requires new functional checks for form visibility and chart empty states, plus deliberate review of baseline updates.
