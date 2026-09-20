# Figma and implementation review

**Follow-up completed:** The Pro copy enabled the [visual review](figma-visual-review-2026-09-20.md) and [frontend implementation workplan](frontend-implementation-workplan-2026-09-20.md). The screenshot limitation described below records the original pass; the follow-up now covers all 11 UI screens and widgets, with proposal overviews and selected enlarged slides. Backend-dependent work is explicitly deferred.

Reviewed 20 September 2026 against local commit `14a7781` (`design updates`). This is an analysis; no application code or Figma designs were changed.

The implementation already satisfies much of the design's hierarchy and decluttering intent. The most important remaining work is functional: the dataset library is unreachable, some model actions disappeared when their containing panel was removed, and evidence limitations are too easy to miss. Several newer implementation choices are sensible improvements on the mockups and should be retained.

## Coverage and confidence

Read the complete metadata trees returned for all three supplied pages: 13 slides in **Suggestions on Hierarchy and Navigation 1**, nine slides in **Suggestions on Hierarchy and Navigation 2**, and 11 screen frames plus the nine-frame **Widgets** section in **UI 1**. Extracted every text-layer name and the explicit annotations. The second suggestions page contains no additional unique text-layer copy relative to the first; it presents the proposed screens without the original critique annotations. That does not establish identical styling or geometry.

Compared these with the React rendering paths, components, CSS, relevant dataset APIs, existing visual baselines, and fresh desktop/mobile UI test runs. Inspected one newly retrieved Figma project-selection screenshot and local implementation screenshots.

**Visual limitation:** Figma reached its View-seat MCP call limit before further screenshots or resolved component context could be retrieved. Metadata does not resolve every component instance's displayed text, typography, color, interaction, or variant. This report therefore provides a comprehensive annotation and implementation comparison, but not a complete pixel-level or prototype-interaction audit. Exact visual fidelity for the remaining Figma screens is unverified. Layer names such as `label`, `value`, and `CTA Text` are not treated as the actual displayed copy.

Sources:

- [Suggestions on Hierarchy and Navigation 1](https://www.figma.com/design/30Mayb6ME7CxJqhfdAO9Aq?node-id=1-3)
- [Suggestions on Hierarchy and Navigation 2](https://www.figma.com/design/30Mayb6ME7CxJqhfdAO9Aq?node-id=709-3739)
- [UI 1](https://www.figma.com/design/30Mayb6ME7CxJqhfdAO9Aq?node-id=746-459)
- [Extracted page inventory, text-layer names, and annotations](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/docs/reviews/figma-2026-09-20-evidence.json)

## Highest-priority improvements

### 1. Restore an accessible, reusable dataset library — high priority

**Design intent:** Projects and Datasets are separate, discoverable destinations. A shared library supports upload, management, deletion, and assignment across projects. This is explicit in [slides 3–4](https://www.figma.com/design/30Mayb6ME7CxJqhfdAO9Aq?node-id=1-207) and the [Dataset Page](https://www.figma.com/design/30Mayb6ME7CxJqhfdAO9Aq?node-id=812-7502).

**Current finding:** `UploadedDatasetsPanel` implements upload/create, search, format filtering, rename, version activation, download, deletion, and Add to project. However, it has no render call in the app. The top-level workspace renders projects, a project, setup, or results; no dataset destination is wired in. Model-node dataset controls remain, but do not replace the shared library journey.

**Recommendation:** Add an explicit Projects / Datasets navigation entry and render the existing component. Name the global destination **Dataset library**; reserve **Project data overrides** for a project-filtered view. The current component fetches user-level datasets while its empty-state copy describes “This project,” so restoring the component without clarifying scope would introduce misleading copy.

**Completion criteria:** Starting at the portfolio, a user can open the library, upload a version, assign it to either of two projects, inspect its usage, and delete an unreferenced version. System-managed sources remain distinguishable. A submitted-run reference continues to block deletion with an actionable explanation.

Evidence: [component](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:8554), [workspace rendering](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:10406), [app composition](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:12320), [existing APIs and reference protection](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/backend/api_service/api/routers/datasets.py:24).

### 2. Retain model actions when removing the management sidebar — high priority

**Design intent:** Move duplicate/delete and run-management details into a secondary modal or menu, preserving access while reducing clutter. See [slide 13](https://www.figma.com/design/30Mayb6ME7CxJqhfdAO9Aq?node-id=1-963).

**Current finding:** Completed models open directly into results. That branch omits `runManagementPanel`, which contains the only Delete model control. The results header restores Duplicate model and technical details, but does not receive a deletion callback. Project model cards also have no delete action. Drafts receive a Save draft panel rather than the locked-model action panel, so draft deletion is also absent from the reviewed UI paths.

**Recommendation:** Add a consistent **Model actions** menu on model cards and the model page. Include rename, duplicate, and delete where permitted. Keep existing confirmation and active-execution restrictions. Whether Duplicate stays prominent is a product decision: it is a valid primary action for iterative scenario work, but diverges from the annotated suggestion to make it secondary.

**Completion criteria:** Draft and completed models have a reachable deletion action; queued/running models explain the cancellation requirement; access to actions does not depend on the discarded sidebar. Verify with disposable test records, not real project data.

Evidence: [delete control](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:4752), [results actions](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:6090), [sidebar exclusion](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:10462), [deletion handler](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:11891), [completed-model navigation](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:11993).

### 3. Keep evidence limitations visible while collapsing technical detail — high priority

**Design evidence:** [Output Page 1](https://www.figma.com/design/30Mayb6ME7CxJqhfdAO9Aq?node-id=812-7704) includes model quality, uncertainty, diagnostics, and explicit exploratory-use caveats. The hierarchy notes advocate hiding secondary detail, not concealing information that changes interpretation.

**Current finding:** Overview quality and uncertainty are inside a collapsed Confidence and diagnostics disclosure. Execution warnings are inside Technical details with no visible count in its label. More significantly, `EvidenceBadge` deliberately returns nothing for `exploratory_only` and `not_evaluated`, including on project/model cards. Users can see a successful execution without an equally visible qualification of its evidence quality.

**Recommendation:** Show a compact evidence-status badge beside the model title and on model cards, including **Exploratory only**. Add a warning count or status on the details trigger. Keep long diagnostics collapsed. Treat execution success and evidence suitability as separate concepts.

**Completion criteria:** With placeholder inputs or quality issues, a user sees the evidence limitation before interpreting results or downloading them, without opening a disclosure. This is a presentation recommendation; it does not require an additional approval gate.

Evidence: [suppressed badges](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/domain/evidence.jsx:60), [hidden execution warnings](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:6117), [collapsed quality](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:6300).

### 4. Repair empty-chart behavior and restore useful label search — high priority for the error

**Design evidence:** [Output Page 2](https://www.figma.com/design/30Mayb6ME7CxJqhfdAO9Aq?node-id=812-8921) includes label filtering and Top 20 controls. The widget collection supplies a reusable structure for charts and empty selections.

**Current finding:** `RankedBars` has chart-local Top 10/15/20/30 controls, which appropriately keep display settings near their chart. It has no label-search input. Its empty branch refers to undefined `normalizedFilter`; a direct component evaluation with zero records throws `ReferenceError`, while a populated record renders. An empty filtered or missing dataset can therefore break the results render instead of showing the supplied empty message. This is an implementation defect discovered during the comparison, not an explicit Figma annotation.

**Recommendation:** Fix the empty branch first; distinguish unavailable data from a search with no matches. Restore a chart-local label filter for large technology/region lists, and explain when only the top N entries are shown. Do not reinstate a large page-wide display toolbar merely to copy the mockup.

**Completion criteria:** Empty input renders a useful message; search with zero matches does not throw; Top N and search interact predictably; selecting a geography with no records remains usable.

Evidence: [RankedBars](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:4300), [failing branch](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:4369). Reproduced by transpiling the existing component with the installed Babel package and invoking it with empty versus populated records.

### 5. Provide a complete read-only input summary from results — medium priority

**Design intent:** The completed input configuration remains available through an expandable panel instead of occupying the results page. See [slide 11](https://www.figma.com/design/30Mayb6ME7CxJqhfdAO9Aq?node-id=1-631) and both Output frames.

**Current finding:** Results show six compact configuration fields inline. The detailed locked-input component contains selectors and policy levers, but belongs to the setup canvas; completed-model navigation goes to results. Technical details shows execution metadata and a selected-model record, not the full policy-lever and input-version snapshot.

**Recommendation:** Keep a short context line such as scenario, geography, and year. Add **View inputs** for the immutable configuration: architecture, engine, scenario, pathway, year, profile, policy levers, and dataset versions/provenance. Populate it from the selected persisted run snapshot. It should not require duplicating a model merely to inspect its inputs.

Evidence: [inline context](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:6084), [locked configuration](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:8433), [selected-model detail fields](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:4468).

### 6. Finish the dataset table's decision-support information — medium priority

The Figma dataset table includes size and project usage alongside name, format, date, and actions. The unmounted implementation puts size and project access inside View details, and lists versions as separate rows. Once the library is restored, show compact **size**, **used by N projects**, and **active/version** information where it helps selection; allow inspecting the actual project names. Group versions beneath their dataset if the list becomes long. Preserve version immutability and reference protection. The design's sales/log/product filenames are sample content, not domain requirements, and its Parquet examples do not establish validated backend support.

Evidence: [table and details](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:8941), [upload accept list](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:8841).

### 7. Preserve useful project-card status signals — medium priority

The inspected Figma project card exposes pending/completed runs, reports, exports, geography, type, and last modification. Current cards show model/completed totals, geography, type, and update time, supplemented by generated identity visuals. In-progress/failed counts and report/export counts are not all visible on the portfolio card.

Add compact running/failed indicators where relevant, prioritizing actionable states over decorative detail. Show report/export counts only if users use them to choose a project. Do not restore every mockup field at equal prominence. The existing collapsed archive is a better realization of the original hierarchy advice than the still-prominent archive toggle in UI 1.

Evidence: [project cards](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:9369), [Figma portfolio](https://www.figma.com/design/30Mayb6ME7CxJqhfdAO9Aq?node-id=812-7124).

## Annotation-by-annotation comparison

“Implemented” here means the inspected implementation satisfies the stated intent; it does not assert pixel equivalence.

| Figma suggestion | Current status | Assessment |
|---|---|---|
| Reduce archive prominence — page 1 slides 2–3 | Implemented | Archived projects sit in a collapsed section below the active grid. Retain. |
| Give datasets a separate page — slides 3–4 | Missing from navigation | Component and APIs exist, but the component is not mounted. Highest-priority restoration. |
| Support dataset upload/manage/delete/reuse — slide 4 | Partial | Library implementation exists; users cannot reach its shared workflow. Node-level data controls are a different path. |
| Make project the parent of models — slides 5–6 | Implemented | A separate project page and non-tab project context replace the peer Project tab. |
| Put return navigation on the left — slide 6 | Implemented | Back to projects / Return to project are explicit left-side controls. Desktop and mobile checks exercise this. |
| Remove the redundant plus model tab — slides 5–6 | Implemented | Run tabs switch models; New model is a named action on the project page. |
| Separate selection from comparison — slides 5–7 | Implemented, adapted | Model selection leads to a dedicated comparison view with Back to models. No need to restore permanent Selection/Comparison tabs. |
| Use fewer primary actions — slides 5–7 | Mostly implemented | New model is primary; comparison and exports are secondary. Duplicate remains primary on results, a deliberate choice to reconsider. |
| Keep primary-button styling consistent — slides 7–10 | Partial | The orange run action has become blue. Different primary selectors still use teal, blue, or gradients; consolidate semantic tokens if a single visual language is desired. |
| De-emphasize layout tools — slides 8–10 | Implemented in intent | Graph-display tools are secondary; visibility is retained for discoverability. Desktop toolbar snapshot currently differs from its baseline. |
| Distinguish disclosure from execution — slides 8–10 | Implemented through a different pattern | Validation counts and a diagnostic dialog replace the old action-like reveal. A modal is reasonable for long diagnostics; no need to force an accordion everywhere. |
| Collapse completed input context — slides 9–11 | Partial | Large input controls disappear, but the full read-only inputs are not exposed from results; six fields remain inline. |
| Move run management away from results — slides 9–11 | Partial | Sidebar is removed; technical dialog remains. Delete and full input access were not preserved. |
| Make four result views clearly control content below — slides 9, 12 | Implemented | Overview / Energy system / Development / Method are prominent tab controls with selected state and keyboard handling. Architecture can omit irrelevant tabs. |
| Move duplicate/delete to secondary UI — slide 13 | Partial | Duplicate is promoted; completed-model deletion is unreachable. Restore a consistent action menu. |

The relevant frames on suggestions page 2 are slide 2 (portfolio), slide 3 (datasets), slides 4–5 (selection/comparison), slide 6 (pre-run), and slides 7–9 (post-run panels and management). Their extracted text supports the same themes rather than a second independent feature list.

## UI 1 screen and widget coverage

| Figma frame(s) | Implementation comparison |
|---|---|
| Project Selection `812:6947`, `812:7124` | Portfolio grid, project metadata, overflow actions, archive handling exist. Current workspace introduction and identity graphics go beyond the supplied mockup. These variants should not be interpreted as separate product pages. |
| Project Selection `812:7301` | Create-project overlay fields map to the existing project-name, geography, and architecture/type modal. |
| Dataset Page `812:7502` | Shared library is not reachable; its underlying component is largely present. See recommendations 1 and 6. |
| Project Page 1 `812:8383` | Project information, model cards, counts, New model, reports, and exports exist. Secondary artifacts are appropriately collapsed. |
| Project Page 3 `812:8490` | New-model modal supports a name and starting from a base or existing configuration. Existing implementation uses meaningful model choices instead of copying sample filenames. |
| Project Page 2 `812:8630` | Comparison selection is supported with completed-model checkboxes and an explicit Compare models action. |
| Project Page 4 `812:8750` | Actual comparison exceeds the static example: output families, reference model, values/change/both, missing values, and artifact comparisons. Preserve this capability. |
| Input page `812:8163` | Scenario selectors, policy levers, flow nodes, readiness, execution, and draft saving are present. Current Model / Scenario / Execution grouping improves scanning. |
| Output Page 1 `812:7704` | Map, scoped/global results, quality, uncertainty, diagnostics exist. Read-only input access and visibility of evidence limitations need improvement. |
| Output Page 2 `812:8921` | Technology generation/capacity, reliability, and trade charts exist. Chart-local Top N is a useful adaptation; label search and robust empty states need work. |
| Widgets `812:9522` | Two Large, two Medium, two Small, two Extra Small frames plus Building Blocks. Implementation has reusable metric/chart/map components and responsive widget classes; no requirement to impose the mockups' fixed pixel sizes. Exact visual token/variant correspondence remains unverified. |

UI 1 also names a header instance “Language Switcher,” but the one inspected screenshot displays COUNTRY OFFICER in that area. This is not sufficient evidence of a localization requirement. Current code has a user menu and local/backend switch. Confirm role-versus-language intent before adding a language feature or removing the environment selector.

## Additional recommendations derived from the comparison

These are review recommendations, not requirements stated in the Figma annotations.

1. **Give navigation persistent URLs.** Most project/model/comparison navigation is React state; only methodology has explicit hash routing. Support refresh, browser Back, and shareable project/model/result-section URLs. Preserve selected comparison models and clearly handle inaccessible/deleted entities. Evidence: [hash handling](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:10611), [navigation actions](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:12359).
2. **Expose older reports and exports.** Both lists render only the first six items, with no visible View all/pagination control in the reviewed component. Add a route or expandable complete list so decluttering does not hide historical outputs. Evidence: [artifact lists](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/app.jsx:10179).
3. **Consolidate the styling layers.** The shell loads 38 numbered phase stylesheets plus platform styles. They form an accumulated cascade, not a clean current design specification. Consolidate button, disclosure, tab, card, and widget tokens/components while retaining verified behavior. Do this after the functional gaps; avoid a cosmetic rewrite as the first step. Evidence: [stylesheet load order](/Users/ben/Documents/UNDP/SEH/energy-development-modeling/frontend/index.html:4214).
4. **Extend behavioral coverage where the happy paths miss gaps.** Add focused coverage for dataset navigation, completed/draft model actions, exploratory-evidence visibility, empty result charts, and access beyond six artifacts. Existing screenshot tests and component presence did not establish end-user reachability.

## What to retain

The clearer project/model hierarchy, named model-creation dialog, completed-run comparison eligibility, collapsed archive, full-surface card targets, left-side returns, four result-view tabs, chart-local controls, responsive widgets, draft-saving feedback, and richer reference-based comparison all align with or improve on the design intent.

Retain the distinction between geography-filtered outcomes and run-wide results. The implementation already tests map scope and fixed global metrics. Do not make all indicators respond to the map simply for visual consistency, and do not copy repeated example values or placeholder dataset names from Figma into the product.

## Verification and remaining work

- Frontend build completed as part of both existing UI suites.
- Desktop Chrome: **16 passed, 2 failed**. Failures: graph-display toolbar screenshot and projects-overview screenshot.
- Mobile Chrome: **17 passed, 1 failed**. Failure: projects-overview screenshot.
- Combined: **33 passed, 3 failed out of 36**. The recorded failures are visual-baseline mismatches, not evidence by themselves of broken workflows. The failed desktop graph test stops at its screenshot assertion, so its later drag/pan assertions were not completed in that run.
- Projects-overview dimensions changed from 1408×652 to 1440×627 on desktop and 388×924 to 412×907 on mobile. Review intended spacing before updating baselines; do not automatically approve the new screenshots.
- Existing automated accessibility checks passed within their tested project/setup regions. This is not a complete accessibility audit of results, dialogs, or the currently unreachable dataset library.
- Tests use mocked APIs. They verify frontend behavior against fixtures, not real solver execution, dataset persistence, or production integration.
- Independently reproduced the empty-chart `ReferenceError` using the current component source; no application files were changed to reproduce it.
- Still needed for a complete visual audit: screenshots/resolved instances for the remaining Figma screens and widget variants, plus prototype interactions. The Figma connector quota blocked that portion.

Recommended sequence: restore dataset and model-action access; fix the empty-chart failure and evidence-status visibility; add the full input summary; then refine library metadata, project-card signals, routing, historical-output access, and the shared styling system. Review and refresh visual baselines only after intended changes are agreed.
