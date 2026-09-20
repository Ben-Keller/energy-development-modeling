# Frontend visual refinements — 20 September 2026

Applied the approved five refinements after the Figma review:

- Shared workspace heading, label and caption sizing, with readable metric labels and tabular numeric values.
- Model cards prioritize name, status, scenario/year and actions; decorative model graphics removed. Project identity graphics retained.
- Results use consistent card padding, chart headings, control sizing and row spacing.
- Workspace destinations, model tabs and result sections have distinct selected states. Result tabs use two columns on small screens.
- The CSS build rebases relative asset URLs when combining subdirectory stylesheets into the root bundle. This fixes missing icons under Project Studio's `/ui/` mount without changing the server.

The preceding refinements also expose existing quality/uncertainty summaries and timestamp-based latest model/report shortcuts.

Live verification: the running `/ui/` landing page and project portfolio loaded without JavaScript errors or failed HTTP responses; icon URLs resolve under `/ui/assets/icons/`. No project records were changed by the smoke check.

Desktop/mobile screenshot baselines were inspected for model cards, chart controls, result actions and model navigation. Backend, runtime, and deployment configuration are unchanged.

## Follow-up: content-first results and card actions

At the user's request, evidence status is now a small keyboard-accessible disclosure beneath the model title; execution limitations and recorded inputs also start collapsed without prominent boxes. The evidence metric summary is inside the existing diagnostics disclosure. All descriptions and recorded values remain accessible.

Exploratory status uses muted neutral styling, with compact text on project/model cards. Model cards place management in an accessible icon button in the header, comparison selection at the left of the footer, and secondary export plus primary Open model actions at the right. Mobile layouts keep a separate selection row and a wide primary open action.

The complete 58-check desktop/mobile suite passed after the layout changes. The final icon-contrast adjustment was checked with the focused comparison/card tests.
