# Match Grant
## Philanthropic Intelligence Platform

**Product, system, and UI specification for an interactive prototype**

Version 0.1 · 19 July 2026 · Prototype definition

**Audience:** Product, design, engineering, prospective foundation users, and implementation partners  
**Status:** Build-ready concept; product assumptions remain subject to user validation

> **Codex build instruction.** Build the interactive front-end prototype defined in Sections 11–14. Treat Sections 1–10 as product truth and design rationale. Use the named routes, demo data, components, interaction states, language rules, and acceptance script. The prototype should feel like a credible working product with simulated data and AI operations, rather than a collection of static mockups.

## Document basis

This specification develops the supplied **Philanthropic Intelligence – Design Brief** and the stakeholder review with Jackson Family Foundation into a complete product and prototype concept. The Jackson discussion is used as a strong lens on relationship-rich family foundations; it is not treated as the only market perspective. Requirements for discovery-led, mid-sized, large, and multi-fund grantmakers are included as distinct operating modes or future production requirements.

## Executive product decisions

1. **Match Grant is an intelligence layer around a grants management system, not a replacement for it.** It connects foundation records, public nonprofit data, websites, submitted documents, staff knowledge, and contextual sources around a durable organization record.
2. **The recommended entry product is Diligence + Portfolio Readiness.** It addresses a concrete bottleneck for relationship-rich funders and can be delivered from data they already possess. Discovery remains an important second mode built on the same organization and evidence layer.
3. **The product supports two foundation modes.** “Steward a known network” prioritizes diligence, monitoring, relationship memory, renewals, and future deployment readiness. “Discover aligned organizations” prioritizes landscape search, explicit strategy criteria, comparison, and watchlists. A hybrid mode combines them.
4. **Objective intelligence prepares human judgment.** The product extracts and reconciles facts, shows provenance, identifies missing or conflicting evidence, and drafts materials. It does not decide who should receive funding.
5. **Confidence belongs to each fact and citation.** A polished AI paragraph cannot conceal uncertain table extraction. Users can open the exact source page or table cell, see validation results, and verify or correct a value.
6. **“Capacity to absorb funding” is represented as a capacity evidence profile, not a universal score.** The system shows documented scale, financial position, operating history, delivery evidence, constraints, and unanswered questions. Staff decide whether an organization is ready to consider for a larger grant.
7. **Integration begins with files.** CSV, Excel, document, and email-derived imports create value before direct GMS or mailbox integrations are available. Production adapters can replace or supplement the file workflow later.
8. **The nonprofit Grant Hub is a complementary product surface.** It uses TripIt-like administrative intelligence to structure deadlines, status changes, reporting obligations, documents, and reminders. Its private tenant data remains separate unless the nonprofit explicitly shares a record.

## Contents

1. Product definition and strategy  
2. Users, operating modes, and permissions  
3. Product structure and information architecture  
4. Core concepts and domain model  
5. End-to-end user journeys  
6. Foundation feature requirements  
7. Nonprofit companion workspace  
8. AI, evidence, and responsible-use design  
9. Data and integration strategy  
10. Production system concept  
11. UI and interaction system  
12. Screen-by-screen specification  
13. Prototype build contract  
14. Acceptance script and definition of done  
15. Delivery roadmap and product validation  
16. Open decisions  
Appendices: data contracts, demo fixtures, language patterns, and handoff prompt

# 1. Product definition and strategy

## 1.1 Product vision

Match Grant gives a grantmaker a living, evidence-linked view of every organization it knows: current grantees, former grantees, applicants, referrals, vetted prospects, and organizations found through landscape research. It turns fragmented records into reusable institutional knowledge and makes the next review, renewal, board discussion, or funding expansion faster and more reliable.

The product’s core asset is a connected organization profile. Public identity and filing data form the base. Each foundation adds a private overlay containing its grants, applications, documents, notes, relationship history, tags, review status, and decisions. AI helps structure and synthesize the sources, while staff retain authority over verified facts and judgments.

## 1.2 Problem statement

Grantmakers usually have enough information and too little usable context. Relevant evidence is distributed across a GMS, Form 990s, audits, project budgets, annual reports, websites, email threads, staff notes, spreadsheets, and the memory of individual team members. The same context is reconstructed at multiple points in the grant cycle.

Generic AI tools can summarize an uploaded packet, but the output is fragile when the source is a complex table, disconnected from prior relationship history, or missing geographic and operational context. A row shift in a financial table can change the conclusion. A good summary can also create false confidence if it does not show which claims are current, contradictory, or unverified.

The product opportunity is a source-linked record system that makes AI useful inside a controlled diligence and portfolio workflow.

## 1.3 Positioning

**For foundations and other grantmakers that need to understand organizations across funding cycles, Match Grant is a philanthropic intelligence platform that connects internal relationship records with public and submitted evidence. It prepares verifiable organization profiles, diligence materials, portfolio views, and discovery results so staff can make faster, better-supported human decisions.**

It complements:

- Grants management systems, which remain the system of record for applications, approvals, payments, reporting, and compliance workflow.
- Nonprofit data services, which remain valuable sources of public identity, filing, and sector data.
- Email, document, and spreadsheet tools, which continue to support everyday work.
- General AI tools, which can remain useful for ad hoc drafting and research.

Match Grant supplies the durable organization, evidence, relationship, and reuse layer that those tools do not provide together.

## 1.4 Recommended product wedge

The first production wedge should be **foundation-side diligence and portfolio readiness**:

- Import current grantees, prior grantees, and vetted prospects.
- Build source-linked organization profiles from foundation records and public data.
- Extract and verify 990, audit, budget, Schedule F, and proposal information.
- Prepare editable diligence and renewal briefs.
- Maintain a living pipeline of current partners, future prospects, high-capacity partners, and research gaps.
- Show what is known, what changed, and what requires follow-up.
- Support future funding scenarios without automatically recommending an allocation.

This wedge solves a visible staff-capacity problem, works with a known universe of organizations, and creates the structured data foundation required for credible discovery later.

Discovery should remain prominent in the prototype because it may be the primary value proposition for foundations that have a strategy but lack a trusted network. The production sequence can still begin with evidence and relationship workflows.

## 1.5 Product principles

### Evidence before fluency

Every consequential factual statement should trace to a source. The interface should make it easier to inspect evidence than to accept a polished paragraph.

### Human judgment has an explicit home

Objective evidence, AI interpretation, and staff assessment are visually and structurally distinct. Staff conclusions are never silently generated or overwritten.

### Relationship context is first-class data

Why an organization entered the pipeline, who knows it, what was learned, what was decided, and when to revisit it should persist across staff changes and grant cycles.

### Administrative intelligence should feel automatic

Imports, emails, documents, and public updates should become structured records, dates, tasks, and reminders through a short confirmation workflow.

### Configuration should follow operating mode

A small family foundation should see a simple, decision-oriented workspace. A larger foundation can add programs, review templates, permissions, and integrations without changing the underlying product model.

### Small and local organizations should not be penalized by proxy metrics

Overhead, salary, travel, organization size, country context, and revenue concentration are prompts for interpretation. They are not universal evidence of quality, efficiency, safety, or impact.

### The system should preserve uncertainty

Unknown, outdated, conflicting, and partially supported information remains visible. The product does not smooth incomplete evidence into false precision.

## 1.6 Goals

### User goals

- Reduce time spent reconstructing an organization’s history and current position.
- Increase confidence in extracted financial and geographic facts.
- Make diligence questions more specific and source-based.
- Preserve relationship knowledge across people and funding cycles.
- See renewals, obligations, data gaps, and changes before they become urgent.
- Maintain a credible pool of organizations for future giving expansion.
- Help discovery-led funders explore organizations against explicit strategy criteria.
- Produce board-ready materials without disconnecting the summary from its evidence.

### Product goals

- Establish the organization profile and evidence model as the common layer across workflows.
- Make staff verification a fast, ordinary part of the interface.
- Demonstrate value from upload-first onboarding.
- Support both relationship-led and discovery-led foundations without splitting the system into two products.
- Create a responsible foundation for later monitoring, connectors, and cross-source analytics.

## 1.7 Non-goals

Match Grant does not:

- Replace a GMS, accounting platform, payment system, applicant portal, or records-retention system.
- Assign a universal “quality,” “impact,” “risk,” or “worthiness” score.
- Rank applicants for funding or make a funding decision.
- Make fraud, misconduct, or compliance accusations.
- Predict social impact from financial or web data.
- Treat administrative-cost ratios as a proxy for effectiveness.
- Treat political or security conditions in a country as evidence against an organization.
- Claim that its organization landscape is complete.
- Expose one foundation’s private relationships, notes, documents, or decisions to another.
- Allow a chat answer to become an authoritative record without source review.

## 1.8 Success measures

The first pilots should measure workflow and evidence quality rather than whether the system “chooses better grantees.”

| Measure | Definition | Initial pilot target |
|---|---|---|
| Time to first usable portfolio | Time from receiving a standard grantee/prospect export to a matched, reviewable portfolio | Same working day for a clean file |
| Diligence preparation time | Median staff time to prepare a standard review packet before and after Match Grant | At least 40% reduction |
| Critical extraction accuracy | Exactness of high-value financial, date, and geography fields after validation | At least 98% on agreed fields |
| Citation validity | Share of generated factual statements that open the correct supporting source location | At least 99% |
| Unsupported-claim rate | Factual memo claims with no supporting evidence | Below 1%; zero for high-severity fields |
| Verification efficiency | Median time to confirm or correct a surfaced fact | Under 30 seconds |
| Institutional memory coverage | Pipeline records with a rationale, owner, status, and next action | At least 90% |
| Deadline capture | Known reporting and renewal dates represented in the system | At least 95% |
| User trust | Staff agreement that the product makes uncertainty and sources clear | At least 4 of 5 |

# 2. Users, operating modes, and permissions

## 2.1 Foundation segments

| Segment | Typical operating reality | Primary need | Product emphasis |
|---|---|---|---|
| Relationship-rich family foundation | Small team, strong referrals, known backlog, board involvement, limited staff capacity | Diligence, relationship stewardship, portfolio memory, future deployment readiness | Steward mode, concise board outputs, simple workflows |
| Discovery-led or newer foundation | Clear strategy, fewer trusted relationships, active sourcing | Credible landscape exploration and preservation of sourcing rationale | Discover mode, transparent criteria, source coverage, watchlists |
| Mid-sized institutional foundation | Several program teams, repeat review cycles, grants operations staff | Standardized review, collaboration, portfolio analysis, renewal monitoring | Templates, assignments, program views, audit history |
| Large or multi-program foundation | Complex permissions, multiple taxonomies and systems, high document volume | Integration, entity resolution, cross-program knowledge, governance | SSO, APIs, fine-grained permissions, configurable data model |
| Community foundation or philanthropic advisor | Multiple funds or donor mandates, overlapping organizations, segmented access | Fund-level views and restrictions with shared organization knowledge | Multi-fund overlays and delegated access; post-MVP |
| International grantmaker | Cross-border grants, Schedule F relevance, currency and country context | Geographic evidence, operating context, local-partner visibility | Multi-currency, geographic reconciliation, dated context notes |

## 2.2 Primary personas

### Foundation director or board liaison

Needs a clear picture of current partners, upcoming decisions, future funding options, concentration, and unresolved questions. Values concise memos and defensible source trails.

### Program officer

Owns relationships and substantive review. Needs organization history, current evidence, comparison across periods, notes, tasks, and an editable assessment area.

### Grants or operations manager

Owns intake quality, documents, deadlines, reporting status, tax status, data hygiene, templates, and exports. Needs reliable extraction and exception queues.

### Research or strategy analyst

Explores landscapes, translates strategy into filters, compares visible organizations, saves searches, and maintains prospect lists. Needs transparent query logic and coverage indicators.

### Reviewer or board member

Needs a read-only, concise packet with the ability to open evidence and leave questions. Should not see internal notes unless specifically permitted.

### Foundation administrator

Controls users, programs, tags, review templates, data sources, thresholds, permissions, and integrations.

### Nonprofit development or operations lead

Tracks opportunities, applications, awards, reporting commitments, documents, reapplication dates, and internal owners. Values automatic extraction from email and files.

## 2.3 Foundation operating modes

Mode changes onboarding, default navigation emphasis, home-page content, and suggested actions. It does not remove capabilities.

| Mode | Setup question | Default home emphasis | Suggested first action |
|---|---|---|---|
| Steward a known network | “Do you already have more credible organizations than you can currently fund or manage?” | Renewals, open diligence, relationship health, data freshness, future-ready pool | Import current grantees and vetted prospects |
| Discover aligned organizations | “Do you have funding priorities but need to identify credible organizations?” | Strategy criteria, landscape coverage, saved searches, new prospects | Define a strategy lens and search universe |
| Hybrid | “Do you need to steward current partners and expand the pipeline?” | Balanced portfolio and landscape view | Import known organizations, then define gaps |

Users can switch the home-page lens at any time. The selected mode is visible as a quiet workspace label, not a permanent product edition.

## 2.4 Roles and permissions

| Capability | Admin | Director | Program staff | Grants ops | Reviewer/board | Analyst |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| View permitted organizations | Yes | Yes | Yes | Yes | Assigned only | Yes |
| Import and resolve records | Yes | View | Limited | Yes | No | Limited |
| Upload and classify documents | Yes | Limited | Yes | Yes | No | Limited |
| Verify extracted facts | Yes | Yes | Yes | Yes | No | Limited |
| Edit relationship assessment | Yes | Yes | Yes | Limited | Comment only | Limited |
| View restricted notes | Configurable | Configurable | Configurable | Configurable | No by default | No by default |
| Create diligence case | Yes | Yes | Yes | Yes | No | Limited |
| Generate/export memo | Yes | Yes | Yes | Yes | View assigned | Limited |
| Change pipeline status | Yes | Yes | Yes | Limited | No | Yes |
| Configure templates/taxonomy | Yes | Limited | No | Limited | No | No |
| Manage users/integrations | Yes | No | No | No | No | No |

Production permissions should support program-, fund-, organization-, document-, and field-level restrictions. The prototype simulates Admin, Program Officer, and Reviewer views.

# 3. Product structure and information architecture

## 3.1 Product shape

The product has one shared intelligence core and several task-oriented workspaces.

~~~mermaid
flowchart TB
    A["Foundation workspaces<br/>Portfolio · Pipeline · Diligence · Landscape"] --> B["Organization + evidence layer<br/>Identity · facts · sources · relationships · history"]
    C["Nonprofit Grant Hub<br/>Opportunities · deadlines · reporting · documents"] --> B
    B --> D["Source and integration layer<br/>GMS exports · filings · websites · documents · email"]
~~~

The nonprofit workspace uses compatible organization, grant, document, date, and evidence concepts, but private tenant records remain separate. A later consent-based exchange can allow a nonprofit to send a verified profile or reporting packet to a funder.

## 3.2 Foundation navigation

The desktop application uses a persistent left navigation and a global top bar.

**Primary navigation**

1. Overview
2. Organizations
3. Pipeline
4. Diligence
5. Portfolio
6. Landscape
7. Tasks
8. Data Inbox

**Persistent utilities**

- Global organization and document search
- Ask Match Grant
- Create button: organization, diligence case, watchlist, task, import
- Notifications
- Workspace and role switcher
- Help and source-language guide
- Settings and integrations

## 3.3 Workspace responsibilities

### Overview

Decision-oriented home surface. It answers: What needs attention, what changed, and what is coming next?

### Organizations

Master list and profile access for every known organization. It is the entry point for entity resolution, saved views, and bulk review.

### Pipeline

Living relationship and prospect workflow. It preserves status, rationale, owner, next action, readiness classification, and research gaps.

### Diligence

Case-based review workspace that combines a request, structured evidence, source documents, flags, questions, staff judgment, and memo output.

### Portfolio

Roll-up of current and past grant relationships. It supports renewal planning, concentration views, data freshness, reporting status, and factual portfolio analysis.

### Landscape

Discovery and research environment using explicit filters, natural-language queries, maps, comparison, source coverage, and watchlists.

### Tasks

Assignments, due dates, follow-ups, and review queues across organizations and grants.

### Data Inbox

Imports, new documents, unmatched organizations, extraction exceptions, new filings, email-derived dates, source conflicts, and update suggestions.

## 3.4 The organization profile as the system spine

Every workspace returns to the same organization profile. It combines:

- Canonical identity and external identifiers.
- Current and historical public facts.
- Foundation-specific relationship status and history.
- Grants, applications, projects, and reporting obligations.
- Documents and citations.
- Structured financial, geographic, programmatic, governance, and operating facts.
- Evidence conflicts and verification history.
- Staff notes, assessments, tasks, and decisions.
- Pipeline membership, watchlists, and saved research rationale.
- Data freshness and coverage.

The profile should remain useful even when no AI summary is shown.

# 4. Core concepts and domain model

## 4.1 Vocabulary

| Term | Meaning |
|---|---|
| Organization | Canonical nonprofit or partner entity, anchored by EIN or another stable identifier where available |
| Public organization core | Shareable public identity, filing, and public-web evidence that may be reused across tenants |
| Foundation relationship | Private tenant overlay describing grants, applications, notes, ownership, status, and decisions |
| Source | A filing, audit, budget, proposal, report, webpage, email, dataset row, or staff-authored record |
| Fact | A typed claim with period, unit, source, extraction method, and evidence state |
| Citation | Exact source location supporting a fact or generated statement; may include page, table, row, cell, URL, and retrieval date |
| Conflict | Two or more sources that materially disagree or apply to unclear periods/scopes |
| Signal | A neutral, reviewable observation such as a changed value, missing document, or geographic mismatch |
| Diligence case | Time-bounded review of an application, renewal, grant increase, or organization |
| Assessment | Human-authored interpretation or conclusion, stored separately from extracted evidence |
| Pipeline item | Foundation-specific relationship record with stage, rationale, owner, next action, and revisit date |
| Capacity evidence profile | Structured view of evidence relevant to considering a larger grant; it is not an automated score |
| Strategy lens | Explicit user-defined criteria used for landscape search or portfolio comparison |
| Watchlist | Saved set of organizations with rationale, owner, and monitoring preference |

## 4.2 Public core and private overlay

The same organization may be known to several customers. Production architecture should separate:

- **Public core:** legal name, aliases, identifiers, public filings, public webpages, public reports, normalized locations, and public facts.
- **Tenant overlay:** grants, applications, submitted documents, internal notes, contact history, review conclusions, tags, pipeline stages, tasks, and decisions.
- **Tenant-derived facts:** facts extracted from private documents remain private, even when they describe a public organization.

This division reduces duplicate public-data work while protecting each foundation’s relationship intelligence.

## 4.3 Entity relationship model

~~~mermaid
erDiagram
    TENANT ||--o{ RELATIONSHIP : owns
    ORGANIZATION ||--o{ RELATIONSHIP : has
    ORGANIZATION ||--o{ SOURCE : described_by
    SOURCE ||--o{ FACT : supports
    FACT ||--o{ CITATION : cites
    RELATIONSHIP ||--o{ GRANT : includes
    RELATIONSHIP ||--o{ APPLICATION : includes
    RELATIONSHIP ||--o{ PIPELINE_ITEM : tracks
    APPLICATION ||--o| DILIGENCE_CASE : reviewed_in
    DILIGENCE_CASE ||--o{ QUESTION : raises
    DILIGENCE_CASE ||--o{ ASSESSMENT : records
    RELATIONSHIP ||--o{ TASK : requires
    RELATIONSHIP }o--o{ WATCHLIST : appears_in
~~~

## 4.4 Fact model

Each fact should include:

- Field key and human label.
- Value and normalized value.
- Unit, currency, fiscal period, and geographic scope where relevant.
- Organization and optional grant, application, program, or project context.
- Source and exact citation.
- Extraction method: imported, deterministic parse, AI extracted, user entered, or calculated.
- Evidence state.
- Validation results and conflict links.
- Created, reviewed, and superseded timestamps.
- Visibility classification.
- User who verified or corrected it.

### Evidence states

| State | Meaning | Default UI treatment |
|---|---|---|
| Verified | A permitted user checked the value against the cited source | Teal check and verifier/date |
| Supported | Extraction is clear and deterministic checks passed; human verification is optional | Neutral blue source badge |
| Needs review | Scan quality, table structure, ambiguity, or failed validation reduces confidence | Amber review badge and queue |
| Conflict | Current sources disagree or appear to cover different periods/scopes | Split-source badge and comparison action |
| Missing | A required source or field is absent | Gray missing badge and request action |
| Superseded | A newer verified fact replaces this value while preserving history | Muted history treatment |

The interface should avoid confidence percentages. A state plus a short reason is more actionable than “82% confident.”

## 4.5 Relationship and pipeline model

A relationship record belongs to one foundation and contains:

- Relationship status: current grantee, former grantee, active applicant, vetted prospect, early prospect, declined, inactive, or archived.
- Pipeline stage, which is configurable by tenant.
- Source of introduction or discovery.
- Rationale for tracking.
- Relationship owner and collaborators.
- Last meaningful interaction and next action.
- Revisit date.
- Programs, geographies, populations, and custom tags.
- Staff-only assessment.
- Readiness decision: ready to consider, monitor, research needed, or not currently pursuing. This is human-set.
- Capacity evidence profile and its coverage.
- Grants, applications, and decision history.

## 4.6 Capacity evidence profile

The profile organizes evidence that may be relevant when a foundation considers a larger or faster grant. It deliberately avoids a single score.

| Dimension | Evidence shown | Example questions |
|---|---|---|
| Current financial scale | Expenses, revenue, assets, typical grant size, trend, fiscal period | How large would the proposed grant be relative to current operations? |
| Liquidity and flexibility | Cash, current assets/liabilities, unrestricted net assets where available | Does the organization appear able to manage timing or reimbursement constraints? |
| Revenue structure | Concentration, public support, earned revenue, multi-year pattern | Would a larger grant materially change revenue concentration? |
| Delivery history | Prior grant size, reporting, documented project completion, scale of activities | Has the organization managed comparable work or funding? |
| Team and controls | Staffing evidence, audit status, finance systems, governance materials | What operating systems would need to expand? |
| Geographic operating evidence | Schedule F, local partners, offices, prior spending, program history | Is there documented experience in the proposed geography? |
| Executable opportunity | Current proposal, pipeline, budget, implementation plan, timing | Is there a concrete use for additional funding within the selected horizon? |
| Relationship knowledge | References, site visits, staff history, unresolved questions | What does the foundation know directly, and what remains untested? |

For each dimension, the system shows **documented**, **partially documented**, **conflicting**, **not documented**, or **not applicable**, plus the sources and dates. A staff user separately selects the relationship’s readiness status.

# 5. End-to-end user journeys

## 5.1 Journey A: onboard a relationship-rich foundation

**Trigger:** A foundation has current grantees, prior applicants, and a vetted backlog but no unified intelligence layer.

1. Admin selects “Steward a known network.”
2. Admin uploads a CSV or Excel export containing organizations, EINs, grants, tags, owners, and statuses.
3. The system maps columns and proposes entity matches.
4. Exact EIN matches are accepted automatically; ambiguous name/address matches enter a review queue.
5. Admin imports a prospect spreadsheet and maps the existing rationale/status columns.
6. The system creates private relationship records around canonical organizations.
7. Public filings and permitted public sources are attached or queued for enrichment.
8. The overview opens with current partners, vetted prospects, renewal timing, stale records, missing sources, and unresolved matches.
9. Admin assigns owners and chooses a standard diligence template.

**Output:** A usable living portfolio and pipeline without replacing the GMS.

**Trust checks:** Import summary, rejected-row file, matching rationale, field-level source attribution, and reversible merge.

## 5.2 Journey B: prepare a diligence memo

**Trigger:** Staff need to review a new proposal, renewal, or potential grant increase.

1. Program officer creates a diligence case from an application or organization.
2. The system assembles existing grants, prior reports, notes, public filings, website context, and uploaded materials.
3. New documents are classified and processed.
4. The extraction workspace surfaces key 990, audit, budget, proposal, and Schedule F fields.
5. Deterministic checks identify table shifts, failed totals, missing pages, incompatible periods, and currency issues.
6. Staff verify high-value fields or correct them while viewing the exact page/table cell.
7. The system compares the proposed activity with prior spending, geography, operating scale, and relationship history.
8. Neutral signals and specific diligence questions are prepared.
9. Staff add their own assessment and conclusion.
10. A board-ready memo is drafted with citations and confidence labels.
11. Staff edit, approve, and export it. The evidence and assessment remain attached to the organization.

**Output:** Editable diligence memo, verified fact set, unresolved questions, and reusable organization history.

**Trust checks:** Claim-level citations, source coverage, memo preflight, human-owned conclusion, and audit log.

## 5.3 Journey C: prepare for future giving expansion

**Trigger:** A foundation may need to deploy more capital and wants to understand which known organizations warrant discussion.

1. Director opens Readiness Planner.
2. Director sets an exploratory scenario: additional amount, time horizon, program/geography, and eligible relationship pools.
3. The system displays current partners and vetted prospects with objective ratios, evidence coverage, readiness status, and open questions.
4. Staff can compare a scenario grant with each organization’s budget, recent revenue, prior grant history, and executable opportunities.
5. Organizations with missing evidence remain visible and are labeled accordingly.
6. Director saves a shortlist for discussion and assigns follow-up research.
7. The system does not allocate the amount or rank organizations by worthiness.

**Output:** A discussion-ready pool of organizations with evidence and research needs.

## 5.4 Journey D: monitor a portfolio and prepare renewals

1. Overview shows upcoming renewals, reporting dates, stale profiles, new filings, and changed facts.
2. Program officer opens a renewal case from a notification.
3. “Since last review” summarizes verified changes in grants, filings, documents, leadership, geography, and staff notes.
4. Staff resolve conflicts and request missing information.
5. Renewal brief reuses prior evidence and shows what changed.
6. Completed work updates the organization profile and next review date.

## 5.5 Journey E: discover organizations against a strategy

1. Analyst creates a strategy lens using explicit criteria: issues, geographies, populations, organization scale, keywords, exclusions, and desired evidence.
2. Landscape translates the criteria into editable filters.
3. Results show organizations, matching criteria, missing data, source coverage, and relationship history.
4. Analyst can use natural language; the interpreted filters appear before results.
5. Similarity to a known grantee is explained by shared attributes rather than an opaque score.
6. Analyst compares organizations and saves selected records to a watchlist with a rationale and next action.
7. New public data or staff research can update the watchlist later.

## 5.6 Journey F: nonprofit email-to-grant record

1. Nonprofit user connects or forwards a grant-related email in a future production workflow. The prototype uses a simulated inbox.
2. Match Grant extracts funder, opportunity, amount, status, deadline, reporting dates, attachments, and action items.
3. The user reviews highlighted source text and confirms or corrects each item.
4. A grant/opportunity record, calendar entry, tasks, and document links are created.
5. Later emails update the same record and preserve the change history.
6. The dashboard shows deadlines, pending submissions, award status, reports, and reapplication reminders.

# 6. Foundation feature requirements

## 6.1 Import and entity resolution

### Required capabilities

- Accept CSV and Excel organization, grant, application, and prospect files.
- Accept folder or multi-file document uploads in a later production build; simulate in prototype.
- Provide mapping templates for common exports and remember tenant mappings.
- Match by EIN first, then normalized name, former name, address, website domain, and user-confirmed aliases.
- Show match reason and confidence category.
- Prevent silent merges.
- Allow create-new, merge, keep-separate, and defer actions.
- Preserve original values and import provenance.
- Produce an import summary and downloadable exception report.
- Support incremental updates without duplicating grants or organizations.

### Prototype behavior

The Data Inbox includes a four-step import wizard with a sample file:

1. Upload
2. Map columns
3. Resolve five proposed matches
4. Confirm import

At least one ambiguous match and one duplicate grant should require user action.

### Acceptance criteria

- User can complete the sample import without leaving the route.
- Mapped columns and decisions persist during the session.
- Organization counts and inbox status update after confirmation.
- The user can undo the simulated import from the completion screen.

## 6.2 Organization directory

### Required capabilities

- Search name, EIN, alias, program, geography, relationship status, owner, and tags.
- Filter by data freshness, evidence coverage, open questions, grant status, and pipeline stage.
- Save personal or shared views.
- Bulk assign owner, tag, watchlist, or research status.
- Export current filtered results.
- Surface possible duplicates without blocking ordinary use.

### Default columns

Organization, relationship, primary programs, geographies, latest operating expenses, active commitment, owner, next decision, evidence status, and last updated.

No generic AI score column appears.

## 6.3 Organization 360 profile

### Header

- Legal and preferred name, EIN, tax status, location, website.
- Relationship status, owner, primary tags, last verified date.
- Active grants and applications.
- Human-set readiness status.
- Actions: create diligence case, add note, add task, add to watchlist, export profile.

### Tabs

1. Overview
2. Financials
3. Programs & Geography
4. Grants & Relationship
5. Documents & Sources
6. Diligence
7. Activity

### Overview content

- Concise source-linked organization description.
- Foundation relationship summary.
- “Since last review” changes.
- Open questions and missing evidence.
- Capacity evidence profile.
- Current grants/applications.
- Upcoming dates.
- Source coverage and freshness.

### Financials content

- Three- to five-year revenue, expenses, assets, liabilities, and net assets.
- Statement-of-activities values from audits where available.
- Key 990 Part IX functional expense categories.
- Salary and travel values with exact row citations.
- Field/program versus U.S.-based or headquarters spending only when a defensible source classification exists.
- Revenue concentration and grant-size ratios as descriptive metrics.
- Source and period comparison.
- Conflict and verification queue.

### Programs & Geography content

- Program descriptions and populations served with source dates.
- Claimed and documented operating geographies.
- Schedule F regions/countries and amounts by fiscal year.
- Proposed-project locations.
- Mismatch view that distinguishes timing, scope, and source limitations.
- Dated contextual notes from approved external sources, separated from organization evidence.

### Acceptance criteria

- Clicking any displayed fact opens its evidence drawer.
- Users can distinguish public facts, foundation-private facts, AI-prepared synthesis, and staff assessment.
- The profile remains coherent when data is sparse.
- The user can correct a fact without editing the original source.

## 6.4 Diligence case

### Case types

- New application
- Renewal
- Grant increase
- Organization review
- Rapid context update

### Standard diligence sections

1. Request at a glance
2. Organization and relationship history
3. Financial position and trends
4. Budget and use of funds
5. Programs, geography, and operating model
6. Governance and controls
7. Capacity evidence profile
8. Contextual considerations
9. Missing or conflicting information
10. Diligence questions
11. Staff assessment
12. Recommendation or decision field, always human-authored
13. Sources

### Neutral signal categories

- Missing source
- Incomplete source
- Extraction needs review
- Source conflict
- Material change
- Claim/evidence mismatch
- Period mismatch
- Geography requires clarification
- Budget assumption requires clarification
- Capacity evidence gap
- Context update

The product must use “review,” “clarify,” or “verify” language. It should not label an organization suspicious or risky based on a detected anomaly.

### Table verification workspace

The financial-document reviewer is a defining feature:

- Original page or spreadsheet region on the left.
- Extracted table and normalized values on the right.
- Selected extracted cell highlights the source row and column.
- Column headers, row labels, fiscal year, unit, and currency are shown.
- Deterministic checks show whether totals reconcile and whether expected rows are present.
- “Shift suspected” appears when row associations or totals do not reconcile.
- User can adjust the selected source cell, correct the normalized value, and mark verified.
- Corrections become training/evaluation examples without changing the source.

### Diligence questions

Questions are source-linked and editable. Each question contains:

- Neutral question text.
- Why it was raised.
- Supporting or conflicting sources.
- Owner and status.
- Optional response and resolution.
- Include/exclude control for memo export.

### Acceptance criteria

- A case can be completed without using the chat interface.
- At least one low-confidence table value can be corrected and verified.
- At least one claim/evidence mismatch can be resolved or left open.
- Staff assessment is visually distinct and never prefilled as an AI conclusion.
- Generated memo contains citations for factual claims and identifies unresolved items.

## 6.5 Pipeline and relationship stewardship

### Default stages

1. New lead
2. Research needed
3. Vetted
4. Ready to consider
5. Invited / active application
6. Current grantee
7. Deferred / revisit
8. Inactive

Tenants can rename or reduce stages in production. The prototype supports board and table views using these defaults.

### Pipeline card

- Organization and status.
- Primary program/geography.
- Relationship owner.
- Why tracked.
- Last interaction.
- Next action and date.
- Evidence coverage.
- Human-set readiness.
- Open question count.

### Required behaviors

- Move stage through menu or drag-and-drop.
- Require a reason when moving to deferred or inactive.
- Preserve full stage history.
- Add a revisit date and reminder.
- Filter to current grantees, high-capacity partners, vetted prospects, and research gaps.
- Save a view as a watchlist.

## 6.6 Portfolio intelligence

### Portfolio questions

- What organizations and grants are active?
- What renewals, reports, or decisions are approaching?
- Which profiles or sources are stale?
- What changed since the last review?
- How is funding distributed by program, geography, organization scale, and relationship tenure?
- Where is the portfolio concentrated?
- Which current partners have documented opportunities or capacity relevant to future expansion?
- Where does evidence remain thin?

### Default portfolio metrics

- Active partners
- Active committed amount
- Renewals in 90 days
- Reports due in 60 days
- Profiles needing review
- New material changes
- Human-designated ready-to-consider pool

### Visualizations

- Funding by program and geography.
- Renewal timeline.
- Organization operating budget versus active grant amount.
- Relationship status distribution.
- Data freshness and evidence-coverage distribution.
- Multi-year funding by organization.

Charts are interactive filters. They do not claim to measure impact.

## 6.7 Readiness Planner

### Scenario inputs

- Additional amount to explore.
- Time horizon.
- Program/geography criteria.
- Current partners, vetted prospects, or both.
- Minimum evidence requirements.
- Optional user-defined maximum grant-to-budget ratio for attention, clearly labeled as a review threshold.

### Result fields

- Organization.
- Human-set readiness.
- Current operating scale and source period.
- Active and historic grant amounts.
- Scenario grant as a percentage of operating expenses.
- Capacity evidence coverage by dimension.
- Documented executable opportunity.
- Open questions.
- Owner and next action.

### Responsible-use rule

The planner may sort by objective columns or a user-selected field. It must not produce an “optimal allocation,” recommended grant amount, or composite readiness score. The user may manually assemble scenarios and compare totals.

## 6.8 Landscape and discovery

### Strategy lens

A strategy lens contains:

- Program areas and keywords.
- Geographies.
- Populations or communities served.
- Organization-size range.
- Desired operating characteristics.
- Evidence requirements.
- Explicit exclusions.
- User explanation of the strategy.

### Search modes

- Structured filter search.
- Natural-language search translated into visible filters.
- Similar-to-known-organization search using selectable attributes.
- Map/list exploration.
- Saved search and change alerts.

### Result transparency

Each result shows:

- Which explicit criteria matched.
- Which criteria did not match.
- Which criteria are unknown because data is missing.
- Public source coverage and recency.
- Existing foundation relationship, if any.
- Why a similarity match was made.

The product should use “criteria match” rather than “fit score.”

## 6.9 Ask Match Grant

The natural-language interface is a query and synthesis layer over permitted records.

### Supported question types

- Find organizations by structured criteria.
- Summarize an organization with citations.
- Compare factual fields across selected organizations.
- Show upcoming dates or unresolved questions.
- Explain what changed since a prior review.
- Draft a source-linked section of a memo.
- Turn a result set into a saved view or watchlist.

### Response anatomy

1. Short answer.
2. Interpreted scope and filters.
3. Evidence table or records used.
4. Source coverage and limitations.
5. Suggested next actions such as open, save, assign, or export.

### Guardrails

- Query only records the user can access.
- Structured filters are displayed and editable.
- Generated claims require citations.
- If evidence is insufficient, state that directly.
- Do not infer staff judgments from historic decisions.
- Do not answer “Who should we fund?” with a ranked list. Offer to translate the strategy into explicit criteria and show records that match them.

## 6.10 Tasks, alerts, and Data Inbox

### Alert types

- Renewal approaching
- Report or payment milestone due
- Public filing added
- Material fact changed
- Source expired or stale
- Missing required document
- Extraction needs review
- Entity match needs review
- Source conflict
- Revisit date reached
- Email-derived date needs confirmation

### Design

- Alerts group by organization and urgency.
- Every alert explains what changed, the source, and the expected action.
- Users can assign, snooze, dismiss with reason, or convert to task.
- Noise controls operate by alert type and program.

### Data Inbox sections

1. Imports
2. Match review
3. Document processing
4. Fact verification
5. New public evidence
6. Email-derived items
7. Conflicts and exceptions

## 6.11 Memo and export builder

### Outputs

- Diligence memo
- Renewal brief
- Organization profile
- Portfolio snapshot
- Prospect comparison
- Watchlist
- Evidence appendix
- CSV data export

### Memo controls

- Choose template and audience.
- Include or exclude sections.
- Select source cutoff date.
- Edit all prose.
- Lock verified facts.
- Add staff assessment and decision.
- Preflight unsupported claims, unresolved conflicts, stale evidence, and missing citations.
- Export to DOCX and PDF in production; prototype shows preview and simulated download.

# 7. Nonprofit companion workspace

## 7.1 Strategic role

The nonprofit-side Grant Hub addresses a different but adjacent job: keeping the organization’s grant opportunities, submissions, awards, reporting obligations, documents, and reapplication windows organized with minimal manual entry.

The strongest interaction pattern is automatic administrative intelligence. An email or document becomes a proposed structured update; the user confirms it; the grant record, dates, tasks, and source links update together.

This can become:

- A standalone product for nonprofits.
- A low-friction source of cleaner organization-owned records.
- A future consent-based channel for sharing verified data with funders.

It should not be required for a foundation to use Match Grant.

## 7.2 Core nonprofit features

- Opportunity and grant pipeline.
- Email and attachment ingestion.
- Automatic extraction of funder, program, amount, deadline, status, dates, contacts, and requirements.
- Unified grant calendar.
- Reporting obligation checklist.
- Reapplication reminders.
- Document library and reusable organizational facts.
- Task ownership and internal collaboration.
- Source-linked change history.
- Optional export or explicit sharing package.

## 7.3 Nonprofit stages

Researching → Planned → In progress → Submitted → Awarded / Declined → Reporting → Closed → Reapply

## 7.4 Privacy boundary

- Foundation and nonprofit tenants remain separate.
- No funder sees a nonprofit’s internal pipeline, declined opportunities, drafts, or email content by default.
- Sharing is object-specific, explicit, time-stamped, and revocable where operationally possible.
- A shared profile or packet is a versioned copy with a clear source and date.

## 7.5 Prototype scope

Include one complete nonprofit dashboard route with:

- Upcoming deadlines.
- Opportunity pipeline.
- Grant calendar.
- Recent inbox extractions.
- Reporting obligations.
- A review drawer for one email-derived deadline.

The route demonstrates the product opportunity without making the foundation prototype depend on it.

# 8. AI, evidence, and responsible-use design

## 8.1 AI’s role

AI supports five bounded functions:

1. **Extraction:** turn documents, tables, webpages, and emails into proposed typed facts.
2. **Reconciliation:** compare values, periods, scopes, and claims across sources.
3. **Retrieval:** find relevant records and passages across permitted data.
4. **Synthesis:** prepare source-linked summaries, changes, and questions.
5. **Drafting:** produce editable memos, profiles, and explanations from reviewed facts.

AI does not own:

- Entity merges without review when identity is ambiguous.
- Verification of a consequential low-confidence fact.
- Staff assessment.
- Readiness classification.
- Funding recommendation or decision.
- Accusations or conclusions about integrity, efficiency, safety, or impact.

## 8.2 Evidence pipeline

~~~mermaid
flowchart LR
    A["Source received"] --> B["Classify + parse"]
    B --> C["Extract typed facts"]
    C --> D["Run deterministic checks"]
    D --> E["Reconcile across sources"]
    E --> F["Human review when needed"]
    F --> G["Publish to profile"]
    G --> H["Reuse in views + memos"]
~~~

### Stage 1: source intake

- Calculate a content hash and detect duplicates.
- Capture uploader, access classification, organization, date, and original filename.
- Scan for malware in production.
- Retain the original.

### Stage 2: classification and layout parsing

- Classify document type and fiscal period.
- Parse native spreadsheet cells when available.
- Use layout-aware OCR for scanned PDFs.
- Preserve page, block, table, row, and cell coordinates.
- Flag incomplete or corrupted documents.

### Stage 3: typed extraction

Each supported document type has a versioned schema. Extraction returns values, units, periods, source coordinates, and model metadata. Free-form summaries never replace the typed output.

### Stage 4: deterministic validation

Examples:

- 990 totals reconcile to known subtotals.
- Part IX rows map to their printed labels.
- Audit statements balance within tolerance.
- Budget component totals equal the stated total.
- Year headers, currency, and units are consistent.
- Schedule F country and region rows remain associated with the correct amounts.
- Page and attachment counts appear complete.

### Stage 5: reconciliation

- Compare the same field across 990, audit, submitted budget, application, and prior verified record.
- Distinguish period differences from true conflict.
- Preserve all source values.
- Propose a current value only when the precedence rule is clear.

### Stage 6: review

High-value fields, failed validations, poor scans, and source conflicts enter a review queue. A user can verify, correct, defer, or mark not applicable.

### Stage 7: publication and reuse

Verified or supported facts update the organization profile. A generated memo can use only allowed evidence states, according to the selected template policy.

## 8.3 Supported document schemas

### Form 990

Priority extraction should cover:

- Legal identity, EIN, tax year, filing type, and completeness.
- Revenue, expenses, assets, liabilities, and net assets.
- Contributions, program-service revenue, investment income, and other material sources.
- Functional expenses, including compensation, professional fees, travel, occupancy, grants paid, and program-service expenses.
- Officers and key employees where appropriate and permitted.
- Grants and assistance.
- Schedule F activities and expenditures outside the United States.
- Schedule I or other schedules only where the use case requires them.

The system must cite printed row labels and page locations. It should not depend only on inferred row order.

### Audit

- Fiscal period and reporting entity.
- Auditor and opinion type.
- Statement of financial position.
- Statement of activities.
- Cash-flow statement where available.
- Functional expenses.
- Liquidity and restrictions.
- Going-concern language or material control findings only when explicitly present, quoted conservatively, and routed for human review.

### Project and operating budget

- Period, currency, total, categories, and line items.
- Salaries and personnel.
- Travel.
- Program/field costs.
- Headquarters or U.S.-based costs only when explicitly classifiable.
- Indirect/administrative costs.
- Co-financing and funding gap.
- Formula or total validation.

### Proposal/application

- Request amount and duration.
- Problem, activities, outputs, geography, population, partners, staffing, timeline, and budget.
- Claims that can be compared with other sources.
- Commitments and missing responses.

### Grant agreement/report

- Award amount and period.
- Payment and reporting dates.
- Restrictions.
- Deliverables and indicators.
- Changes, variances, and follow-up commitments.

### Email

- Sender/recipient and date.
- Organization/funder.
- Opportunity or grant association.
- Deadline, date, amount, status, request, commitment, attachment, and next action.
- Highlighted source sentence for every proposed structured update.

## 8.4 Financial interpretation rules

- Show source values and trends before interpretation.
- Keep fiscal periods and currencies explicit.
- Use ratios descriptively and show the numerator, denominator, and source years.
- Treat user-defined thresholds as attention rules, not standards of quality.
- Do not infer “too much” salary, travel, overhead, or headquarters spending from a ratio alone.
- When comparing field and U.S.-based spending, display the classification method and unclassified amount.
- Separate audited figures, tax filings, submitted budgets, and foundation calculations.
- Flag a row-shift or failed total as an extraction problem, not an organization problem.
- Allow staff to record a contextual explanation next to a factual signal.

## 8.5 Geographic and contextual intelligence

Geographic comparison should distinguish:

- Organization-stated operating locations.
- Locations documented in public filings.
- Proposed project locations.
- Foundation grant locations.
- Physical offices.
- Local partners.
- Financial spending locations.

A mismatch can mean growth, a new partner, an incomplete filing, a broad regional description, or an incorrect claim. The system surfaces the discrepancy and asks for clarification.

Political, security, regulatory, and humanitarian context is maintained as a separate dated source layer:

- Every note shows source, publication date, geography, and retrieval date.
- The interface explains that context describes an operating environment, not organizational quality.
- Material changes can produce a review prompt.
- Staff can select which approved context sources are used.
- Sensitive security analysis can have restricted visibility.

## 8.6 Grounded memo generation

Memo generation should use a fact-and-citation plan:

1. Select reviewed facts and staff-authored assessments permitted for the template.
2. Assemble an outline with source coverage.
3. Draft each section with sentence-level evidence references.
4. Run an unsupported-claim check.
5. Run a period, amount, name, and geography consistency check.
6. Show unresolved conflicts and missing evidence.
7. Require user review before export.

The staff conclusion section is blank by default. If a user asks AI to help edit their own conclusion, the product should preserve authorship and clearly show the change.

## 8.7 Natural-language query design

The model should create an intermediate query plan rather than write unrestricted database queries.

Example:

**User question:** “Show vetted organizations working on maternal health in East Africa that have operated above $3 million and have no open document gaps.”

**Visible interpretation:**

- Relationship stage = Vetted
- Program = Maternal health
- Geography = East Africa
- Latest verified operating expenses ≥ USD 3,000,000
- Missing required documents = 0

The user can edit the filters before or after execution. The answer lists records and coverage limitations. If some organizations lack a current operating-expense fact, they appear under “Unknown,” not as silent exclusions unless the user chooses that behavior.

## 8.8 Evaluation framework

Maintain a versioned evaluation set containing representative:

- Native PDFs, scans, spreadsheets, and mixed-layout documents.
- 990 and Schedule F tables.
- Audits with differing formats.
- Multi-currency budgets.
- Incomplete and amended filings.
- Conflicting periods and organization names.
- Emails containing multiple dates or changed deadlines.

Measure:

- Entity-match precision and recall.
- Document classification accuracy.
- Cell-level extraction exact match.
- Critical-field accuracy.
- Table header/row association accuracy.
- Citation-location accuracy.
- Conflict detection recall.
- Unsupported-claim rate.
- Memo factual consistency.
- Human correction time.

All evaluation results should be segmented by document type and quality. An aggregate accuracy number can conceal the exact failure mode that matters.

## 8.9 Responsible-use controls

- Clear separation of evidence, AI interpretation, and staff judgment.
- No protected-class inference.
- No inferred misconduct.
- No automated eligibility denial or funding decision.
- Bias review for size, geography, language, and data-availability effects.
- Data-minimization rules for personal information.
- Restricted access for sensitive staff notes and security context.
- Prompt and output logging appropriate to privacy requirements.
- Provider settings that prevent training on tenant data.
- Model and prompt version recorded for consequential generated output.
- User-visible correction and feedback path.

# 9. Data and integration strategy

## 9.1 Source layers

| Layer | Examples | Primary use | Core controls |
|---|---|---|---|
| Foundation system records | GMS exports, grant history, applications, reports, tags, decisions | Private relationship and workflow context | Tenant isolation, provenance, field mapping |
| Organization-submitted records | Budgets, audits, proposals, reports, policies | Current first-party evidence | Document permissions, verification, period |
| Public nonprofit data | Government records, filings, approved public datasets | Identity, tax status, financial history | Source date, license, refresh schedule |
| Public web evidence | Organization sites, annual reports, strategy pages, public news | Current programs, leadership, geography, context | Retrieval date, URL, change history |
| Curated/licensed data | Partner or proprietary datasets | Enrichment and landscape coverage | License enforcement, attribution, entitlements |
| Staff-authored knowledge | Notes, references, assessments, decisions | Relationship memory and judgment | Authorship, permissions, audit history |
| Context sources | Approved country, regulatory, security, or humanitarian sources | Operating-environment context | Dated, separate from org judgment, restricted as needed |

## 9.2 Integration sequence

### Stage 1: upload-first

- CSV/Excel import.
- Bulk document upload.
- Manual website and source links.
- Export to DOCX, PDF, and CSV.

### Stage 2: scheduled exchange

- Secure file drop.
- Scheduled GMS exports.
- Public filing refresh jobs.
- Forwarding inbox for email extraction.

### Stage 3: direct connectors

- GMS API adapters.
- Mailbox and calendar connectors.
- Document-storage connectors.
- SSO and directory sync.
- Approved public/licensed data APIs.

The product should use an adapter interface so the organization, grant, document, and event model remains stable as connectors change.

## 9.3 Import contracts

### Organization import minimum

Organization name and either EIN, website, or address. Optional fields include relationship status, program, geography, owner, tags, rationale, and next action.

### Grant import minimum

Organization reference, amount, currency, award date, and status. Optional fields include program, purpose, start/end, payment dates, owner, report dates, and external record ID.

### Prospect import minimum

Organization name, source/rationale, and current status. The import must preserve free-text rationale even when no entity match exists yet.

### Document import minimum

File, organization or case association, document type if known, date/period if known, and visibility.

## 9.4 Data quality rules

- Original source values are immutable.
- Normalization is versioned.
- Duplicate detection precedes merge.
- Currency conversions show rate source and date when used.
- Dates store original text and normalized value.
- Derived metrics list dependencies.
- Facts expire or become stale according to field-specific rules.
- A newer source does not erase history.
- Staff corrections require a reason when they override a high-authority source.
- Deletion and retention policies differ for public, submitted, and internal data.

## 9.5 Data freshness

Each profile displays freshness by domain:

- Identity/tax status.
- Financials.
- Programs.
- Geography.
- Leadership/governance.
- Foundation relationship.
- Context.

Freshness rules are configurable by source type. “Last updated” should not imply that every field was updated on the same date.

# 10. Production system concept

## 10.1 Architecture approach

Begin with a modular monolith: one web application, one application API, one primary relational database, one object store, and asynchronous workers. Preserve clear service boundaries so high-volume ingestion, search, or AI workloads can separate later without premature operational complexity.

~~~mermaid
flowchart TB
    U["Foundation + nonprofit users"] --> W["Web application"]
    W --> A["Application API / BFF"]
    A --> P["PostgreSQL<br/>tenant records · facts · audit"]
    A --> O["Object storage<br/>originals · previews · exports"]
    A --> S["Search + vector index"]
    A --> Q["Job queue"]
    Q --> X["Document + table extraction"]
    Q --> L["AI orchestration + evaluation"]
    C["Connectors<br/>files · GMS · filings · web · email"] --> Q
    X --> P
    L --> P
~~~

## 10.2 Suggested production stack

This is a reference choice, not a vendor commitment.

| Layer | Suggested approach | Reason |
|---|---|---|
| Web | React/Next.js with TypeScript | Strong data-app patterns, server rendering where useful, shared types |
| API | FastAPI/Python or TypeScript service | Python is convenient for document/AI workflows; typed API contracts remain essential |
| Primary data | PostgreSQL with row-level security | Relational integrity, JSON support, tenant isolation, mature operations |
| Semantic search | pgvector initially; dedicated search service if scale requires | Keeps early architecture simple |
| Keyword/faceted search | PostgreSQL full-text initially or OpenSearch at scale | Supports transparent filters and broad document search |
| File storage | Encrypted object storage | Originals, page images, attachments, and generated exports |
| Async work | Managed queue and worker service | OCR, extraction, refresh, export, and alert jobs |
| OCR/layout | Provider adapter with layout/table coordinates | Avoids locking the evidence model to one vendor |
| LLM | Provider adapter using structured output and grounded prompts | Portability, evaluation, and policy control |
| Identity | Managed identity provider with SSO options | Foundation-grade access and lifecycle management |
| Observability | Structured logs, traces, job metrics, AI evaluation dashboard | Required for data and AI reliability |

## 10.3 Logical modules

### Identity and access

Users, tenants, roles, programs/funds, object permissions, SSO, and audit.

### Organization registry

Canonical identity, aliases, identifiers, locations, public core, duplicate management.

### Relationship and grants

Tenant overlays, grants, applications, pipeline, watchlists, tasks, decisions.

### Source and evidence

Documents, webpages, datasets, facts, citations, conflicts, verification.

### Ingestion

File parsing, connector adapters, entity match, document classification, extraction jobs.

### Diligence and memo

Case templates, signals, questions, assessments, memo generation, export.

### Search and analytics

Structured filters, semantic retrieval, portfolio aggregations, landscape queries.

### Notifications

Dates, source refresh, changes, tasks, email/calendar delivery.

### Nonprofit Grant Hub

Private opportunities, grant records, email-derived events, reporting obligations, and sharing packages.

## 10.4 Key API surfaces

| Endpoint family | Representative operations |
|---|---|
| Organizations | List/filter, get profile, create/merge, aliases, history |
| Relationships | Update status/owner/tags, add note, stage history, readiness |
| Imports | Create, map, preview, resolve, commit, undo, exceptions |
| Sources/documents | Upload, classify, preview, retrieve citation region, visibility |
| Facts | List by domain, compare, verify, correct, supersede, view conflicts |
| Grants/applications | Import, view, update, deadlines, external IDs |
| Diligence | Create case, run checks, manage questions, assessment, status |
| Portfolio | Summary, charts, saved views, scenario data |
| Landscape | Query, interpret criteria, compare, save watchlist |
| Ask | Create safe query plan, execute, synthesize with citations |
| Memos | Draft, validate, edit, version, export |
| Tasks/alerts | Assign, resolve, snooze, preference management |
| Nonprofit | Opportunities, email extractions, obligations, sharing package |

## 10.5 Security and privacy requirements

- Tenant isolation at database and application layers.
- Encryption in transit and at rest.
- Object-level signed access for source files.
- Role-, program-, fund-, and document-level permissions.
- Separate restricted-note class.
- Complete audit log for access to sensitive documents, fact correction, exports, and permission changes.
- Provider data-processing agreements and no-training controls.
- Configurable retention and legal hold.
- Data export and deletion workflows.
- Secrets isolated from application code.
- Malware scan and file-type controls.
- Rate limits and safe query planning.
- Security review before mailbox or GMS connectors.

## 10.6 Reliability and quality requirements

- Idempotent import and connector jobs.
- Retryable asynchronous processing with visible state.
- Original-source retention.
- Versioned extraction schema, prompt, and model.
- Reproducible memo inputs.
- Backups and tested restore.
- Structured error states that tell users what can be retried or reviewed.
- No profile update from a failed or partial extraction unless the user explicitly accepts it.
- Accessibility target: WCAG 2.2 AA.

# 11. UI and interaction system

## 11.1 Experience character

The interface should feel calm, exact, and editorial: a professional research and operating environment rather than an AI demo. Evidence, status, and next actions receive stronger emphasis than decorative analytics.

Avoid:

- AI gradients, glowing effects, and “magic” language.
- Large generic KPI cards that do not lead to work.
- Opaque scores.
- Overuse of red.
- Dense dashboards with every metric visible at once.
- Chat as the only path through the product.

## 11.2 Visual tokens

### Color

| Token | Value | Use |
|---|---|---|
| Ink | #172326 | Primary text |
| Muted ink | #5F6D70 | Secondary text |
| Canvas | #F5F7F5 | Application background |
| Surface | #FFFFFF | Cards, panels, tables |
| Primary navy | #173F5F | Navigation, primary action |
| Primary hover | #0F3048 | Hover/active action |
| Evidence teal | #247A70 | Verified state and positive confirmation |
| Information blue | #3D6F8F | Supported/source-linked state |
| Review amber | #B7791F | Needs review or incomplete evidence |
| Conflict coral | #B6544A | Conflict requiring attention |
| Border | #DCE3E1 | Dividers and controls |
| Pale teal | #E8F3F1 | Selected or verified background |
| Pale amber | #FAF1DF | Review background |
| Pale coral | #F8E9E6 | Conflict background |

Use color with an icon and text label. Never encode state by color alone.

### Typography

- Font: Inter, with a system sans-serif fallback.
- Page title: 28px/34px, weight 650.
- Section title: 20px/28px, weight 650.
- Card title: 15px/22px, weight 650.
- Body: 14px/21px.
- Dense table: 13px/18px.
- Metadata: 12px/17px.
- Numeric values: tabular numerals.

### Spacing and geometry

- 8px base spacing grid.
- Left navigation: 232px expanded, 72px collapsed.
- Top bar: 64px.
- Content maximum width: 1600px; standard page padding 28–32px.
- Card radius: 10px.
- Control radius: 8px.
- Drawer width: 440px standard; 560px for evidence review.
- Dense tables: 44px minimum row; comfortable mode 52px.
- Shadows are subtle and limited to overlays; cards use borders.

## 11.3 App shell

### Left navigation

- Match Grant wordmark and workspace.
- Primary routes.
- Active route uses pale teal background and navy text.
- Counts appear only for actionable queues, such as Diligence 3 or Data Inbox 7.
- Bottom items: Nonprofit demo switch, Settings, user menu.

### Top bar

- Breadcrumb or current page.
- Global search field with keyboard shortcut.
- Ask button.
- Create button.
- Notifications.
- Role switcher in the prototype.

## 11.4 Cross-cutting interaction patterns

### Evidence link

Every factual value can show a compact source token, such as:

**2024 990 · p.10 · row 12**

Clicking opens the Evidence Drawer at the correct location.

### Evidence Drawer

- Source metadata and visibility.
- Page or table preview.
- Highlighted supporting region.
- Extracted value and normalized value.
- Validation results.
- Other sources for the same field.
- Verify, correct, mark conflict, or request follow-up.
- Fact history.

### Status chips

Use short text: Verified, Supported, Review, Conflict, Missing, Stale. Relationship statuses and workflow statuses use a separate visual family so users do not confuse evidence with pipeline state.

### AI-prepared content

AI-prepared paragraphs have a small “Prepared from 6 sources” line. Clicking it opens the source list. There is no repeated sparkle icon.

### Staff assessment

Human interpretation appears in a bordered section labeled with author and last edit. It uses standard text color and a subtle pale-blue left rule.

### Filters

- Active filters remain visible as removable chips.
- “Unknown” is an explicit option.
- Natural-language interpretation produces the same chips.
- Clear-all and save-view actions remain nearby.

### Tables

- Sticky header.
- Sort indicators.
- Column chooser.
- Comfortable/dense toggle.
- Select rows and bulk-action bar.
- Horizontal scroll only when necessary.
- Empty state describes how to obtain data.

### Loading and errors

- Skeletons preserve layout.
- Long jobs show named steps and can continue in background.
- Partial success is shown accurately.
- Error messages state what failed, what remains safe, and the next action.

## 11.5 Language system

Prefer:

- Needs verification
- Source conflict
- Coverage incomplete
- Proposed update
- Evidence suggests
- Requires clarification
- No current evidence found
- Based on the 2024 filing
- Staff assessment
- Ready to consider, set by Maya Chen

Avoid:

- AI approved
- Bad fit
- Suspicious expense
- High-risk organization
- Recommended grantee
- Impact score
- Absorptive capacity score
- Trust score
- Objective truth

# 12. Screen-by-screen specification

## 12.1 Route map

| Route | Screen | Prototype priority |
|---|---|:---:|
| /onboarding | Mode and data setup | P0 |
| /overview | Foundation overview | P0 |
| /organizations | Organization directory | P0 |
| /organizations/:id | Organization 360 | P0 |
| /pipeline | Relationship pipeline | P0 |
| /diligence | Diligence queue | P0 |
| /diligence/:id | Diligence workspace | P0 |
| /portfolio | Portfolio intelligence | P0 |
| /readiness | Future Giving Readiness Planner | P0 |
| /landscape | Landscape and discovery | P0 |
| /tasks | Tasks and alerts | P1, lightweight in prototype |
| /data-inbox | Imports and review queues | P0 |
| /memos/:id | Memo builder | P0 |
| /nonprofit | Nonprofit Grant Hub | P0 concept route |
| /settings | Workspace settings | P1, shell only |

## 12.2 Onboarding

### Purpose

Explain the product in one sentence, select operating mode, and reach useful data quickly.

### Layout

- Simple centered page with product mark.
- Step indicator: Mode → Data → Review → Ready.
- Three large mode cards.
- Recommended label appears on “Steward a known network” for the seeded foundation.
- Data step offers “Use demo data” and “Import a file.”
- Review step shows organization/grant/prospect counts and three match exceptions.

### Key interaction

Selecting a mode changes the preview panel on the right. “Use demo data” completes onboarding and opens the relevant overview lens.

## 12.3 Relationship-led Overview

### Header

“Good morning, Maya” and the subline “Three decisions and seven evidence items need attention.”

### Top summary strip

- 8 current partners
- $4.2M active commitments
- 3 renewals in 90 days
- 5 ready-to-consider organizations
- 7 evidence items to review

Each metric is clickable and filters a relevant screen.

### Main grid

**Left, two-thirds**

- Decision queue: three compact rows with organization, type, due date, owner, and unresolved count.
- Future giving readiness: six-row table with current partners and vetted prospects; show readiness, operating scale, evidence coverage, open questions.
- Recent material changes: new filing, leadership update, project-location change.

**Right, one-third**

- Upcoming dates.
- Data health by domain.
- Recent activity.

### Empty/edge states

No renewals message suggests reviewing the pipeline. Missing financial data presents an import/request action.

## 12.4 Discovery-led Overview

This uses the same route and shell but changes content:

- Current strategy lens.
- Landscape coverage by geography/program.
- Recent organizations matching saved searches.
- Prospects awaiting research.
- Watchlists and source coverage.
- Shortcut to “Describe what you are looking for.”

The mode switch in the page header lets the prototype toggle between the two overview variants.

## 12.5 Organization Directory

### Header

Title, organization count, saved-view selector, Import button, Add organization button.

### Filter bar

Search, relationship, program, geography, owner, readiness, evidence state, updated date, more filters.

### Table

Use 12 fictional records. Default sort is next decision date. Row click opens Organization 360. A bulk-action bar appears when records are selected.

### Demonstrated interactions

- Search by name.
- Apply “Vetted prospects” and “Research needed.”
- Sort by operating expenses.
- Save current filters as “Future expansion pool.”
- Export current view with simulated success toast.

## 12.6 Organization 360: Overview

### Profile header

- “Kijani Health Collaborative” with initials mark.
- Kenya · EIN-equivalent/public identifier shown as available.
- Current grantee.
- Owner: Maya Chen.
- Readiness: Ready to consider, set by staff.
- Active grant: $450K through Dec 2026.
- Last reviewed 18 days ago.

### Overview grid

**Main column**

- Source-linked organization summary.
- Since last review timeline.
- Capacity evidence profile with eight dimensions and evidence states.
- Current grants and proposed opportunity.
- Programs and geography.

**Right rail**

- Open questions.
- Upcoming dates.
- Source coverage.
- Relationship contacts.

### Key interaction

Click “2024 operating expenses: $3.8M” to open the Evidence Drawer. The drawer shows two sources, one verified and one conflicting because the audit covers a consolidated entity.

## 12.7 Organization 360: Financials

### Top

- Period selector.
- Currency display control.
- Verify 2 items button.

### Content

- Revenue/expenses trend line.
- Financial snapshot table with source badges.
- Functional expenses horizontal bars.
- Grant-to-budget context.
- Source comparison table: 990, audit, project budget.
- “Needs review” section with one suspected row shift.

### Key interaction

Open the salary item, compare the extracted row with the page image, correct the value, and mark it verified. The chart and diligence case update.

## 12.8 Pipeline

### Header

Pipeline title, board/table toggle, filters, add prospect.

### Board

Columns: Research needed, Vetted, Ready to consider, Invited, Deferred. Current grantees are available as a filter/view rather than occupying a very wide board.

### Cards

Name, programs, country, owner, rationale, next action, evidence coverage, open questions.

### Key interactions

- Move a card from Vetted to Ready to consider and select a reason.
- Defer a card and require a revisit date.
- Open quick profile without leaving the board.
- Switch to table view.

## 12.9 Diligence Queue

### Sections

- My active cases.
- Awaiting evidence.
- Awaiting staff assessment.
- Ready for memo.
- Recently completed.

Each row shows organization, case type, request, due date, owner, evidence status, open questions, and last update.

## 12.10 Diligence Workspace

### Three-panel desktop layout

**Left panel, 244px**

- Case sections.
- Source document list with processing/evidence status.
- Add source.

**Center panel, flexible**

- Selected section.
- Factual snapshot.
- Signals and comparisons.
- Editable diligence questions.
- Staff assessment block.

**Right panel, 344px**

- Evidence details for selected fact.
- Source list.
- Verification action.
- Case activity.

The right panel can expand into the 560px Evidence Drawer for document review.

### Seeded case

“Kijani Health Collaborative · Grant increase review · $750,000 over 24 months.”

Seeded signals:

- Proposal includes Uganda, while the latest Schedule F documents Kenya only.
- Salary value needs review because the scan parser may have shifted one row.
- Proposed annual amount is 19.7% of latest verified operating expenses.
- Current project budget does not identify the source of one co-financing line.
- Security context note for one implementation region was updated 12 days ago.

All language stays neutral and offers a question.

### Key interactions

- Navigate sections without page reload.
- Verify/correct the salary value.
- Mark the geography question resolved with a staff note.
- Add a custom question.
- Add staff assessment.
- Generate memo.

## 12.11 Evidence Drawer and Table Reviewer

### Evidence Drawer

- Header with document title, period, source type, and visibility.
- Page preview with highlighted region.
- Fact card with extracted and normalized value.
- Validation checklist.
- Other-source comparison.
- Verify, correct, mark conflict, or defer.

### Table Reviewer expanded view

Use a split screen. The left shows a realistic document page representation with a financial table. The right shows extracted cells. Clicking a cell highlights the corresponding source row. A deliberate initial misalignment demonstrates the failure mode and correction.

The prototype can draw the document page as HTML rather than load a real PDF.

## 12.12 Portfolio Intelligence

### Header

Date range, programs, geographies, current/past relationship, saved view, export.

### Top metrics

Active partners, commitments, renewals, reports due, stale profiles, material changes.

### Charts

- Funding by program.
- Geography distribution.
- Operating budget vs active grant scatter.
- Renewal timeline.

### Tables

- Upcoming decisions.
- Concentration by program/geography.
- Profiles needing review.

Charts update smoothly and clicking a chart category applies a visible filter.

## 12.13 Future Giving Readiness Planner

### Scenario bar

- Additional amount: $5,000,000.
- Horizon: 18 months.
- Pool: current partners + vetted prospects.
- Program/geography: All.
- Evidence requirement: no critical missing source.

### Main content

- Manual scenario total and unallocated amount.
- Organization comparison table.
- Expandable capacity evidence profile.
- Research-needed side panel.

### Interaction

Users add a **discussion amount** to selected organizations. The system updates totals and factual ratios, while keeping the label “Exploratory, not a recommendation.” It warns when evidence is incomplete and never blocks the user solely based on a threshold.

## 12.14 Landscape

### Search header

Large prompt field: “Describe the organizations you want to explore.” A structured filter button sits beside it.

### Body

**Left filter rail**

Program, geography, population, organization size, evidence freshness, relationship status, keywords.

**Center**

Map/list toggle and 18 fictional results.

**Right comparison tray**

Up to four selected organizations.

### Result card

Name, description, geographies, operating scale, source freshness, relationship, explicit criteria matches, unknown criteria, and Add to watchlist.

### Key interaction

Run a seeded question, show interpreted filter chips, select two organizations, compare, and save one to a watchlist with rationale.

## 12.15 Data Inbox

### Queue tabs

Imports, Matches, Documents, Verification, Updates, Conflicts.

### Default screen

- Sample portfolio import at 92% complete.
- Two ambiguous organization matches.
- One duplicate grant.
- Three document extraction items.
- One new filing update.
- Two email-derived dates.

### Key interactions

- Complete the sample import wizard.
- Resolve an organization match.
- Open an extraction issue.
- Accept or dismiss a proposed updated fact with reason.

## 12.16 Tasks and Alerts

A compact list grouped by Today, This week, Later, and Snoozed. Filters include owner, program, organization, and alert type. The same item never appears as both an unresolved alert and a duplicate task unless the user converts it.

## 12.17 Memo Builder

### Layout

**Left:** section outline and inclusion controls.  
**Center:** editable memo preview.  
**Right:** source coverage, unresolved issues, and preflight.

### Seeded memo

Grant increase review for Kijani Health Collaborative. The generated sections use superscript-style source markers that open the right source panel.

### Preflight

- All 14 factual statements cited.
- One unresolved geography question.
- One source older than the selected 24-month freshness rule.
- Staff conclusion incomplete.

The user can export only after acknowledging unresolved items; staff conclusion can remain blank in draft status.

## 12.18 Nonprofit Grant Hub

### Header metrics

- 6 active opportunities
- $1.4M submitted
- 3 deadlines in 30 days
- 2 reports due
- 4 inbox items to review

### Main content

- Grant pipeline.
- Calendar/list of deadlines.
- Reporting obligations.
- Recent email extractions.

### Key interaction

Open an email from “Northstar Community Fund.” The system proposes a changed submission deadline, highlights the source sentence, and shows the current stored date. Confirming updates the grant record and calendar and records the source.

# 13. Prototype build contract

## 13.1 Build objective

Create a high-fidelity, desktop-first, interactive front-end prototype that allows a stakeholder to complete the five acceptance scenarios in Section 14. The prototype uses fictional seeded data, simulates AI and processing, and requires no external accounts or services.

## 13.2 Technical stack

- Vite
- React
- TypeScript with strict mode
- React Router
- Tailwind CSS
- shadcn/ui or equivalent accessible primitives
- Lucide React icons
- TanStack Table
- Recharts
- Zustand or a small context/store layer
- React Hook Form where forms are nontrivial
- Vitest and React Testing Library for critical interactions

For the landscape map, use a bundled simplified SVG or react-simple-maps with a local topology file. The app must not depend on live map tiles.

## 13.3 Prototype constraints

- No backend.
- No authentication provider.
- No real organization or foundation data.
- No real AI calls.
- No runtime dependency on external APIs, fonts, images, or map tiles.
- No filler or placeholder copy.
- Simulated operations use believable progress and deterministic results.
- Session changes persist in localStorage and can be reset from the user menu.
- Direct URLs to every route work.
- The app launches with one standard command documented in README.

## 13.4 Project structure

~~~text
src/
  app/
    router.tsx
    AppShell.tsx
  components/
    evidence/
    organizations/
    diligence/
    portfolio/
    pipeline/
    landscape/
    nonprofit/
    ui/
  data/
    fixtures.ts
    documents.ts
    queries.ts
  features/
    overview/
    organizations/
    pipeline/
    diligence/
    portfolio/
    readiness/
    landscape/
    inbox/
    memos/
    nonprofit/
  lib/
    mockApi.ts
    calculations.ts
    formatters.ts
    storage.ts
  store/
    useWorkspaceStore.ts
  types/
    domain.ts
  styles/
    globals.css
~~~

Equivalent organization is acceptable if feature boundaries remain clear.

## 13.5 Core TypeScript contracts

~~~typescript
export type EvidenceState =
  | "verified"
  | "supported"
  | "needs_review"
  | "conflict"
  | "missing"
  | "superseded";

export type RelationshipStatus =
  | "current_grantee"
  | "former_grantee"
  | "active_applicant"
  | "vetted_prospect"
  | "early_prospect"
  | "declined"
  | "inactive";

export type ReadinessStatus =
  | "ready_to_consider"
  | "monitor"
  | "research_needed"
  | "not_currently_pursuing";

export interface Citation {
  id: string;
  sourceId: string;
  label: string;
  page?: number;
  table?: string;
  row?: string;
  column?: string;
  url?: string;
  retrievedAt?: string;
}

export interface Fact<T = string | number | boolean> {
  id: string;
  organizationId: string;
  field: string;
  label: string;
  value: T | null;
  displayValue: string;
  period?: string;
  unit?: string;
  currency?: string;
  scope?: string;
  evidenceState: EvidenceState;
  evidenceReason?: string;
  citations: Citation[];
  extractionMethod: "imported" | "parsed" | "ai_extracted" | "user_entered" | "calculated";
  verifiedBy?: string;
  verifiedAt?: string;
}

export interface Organization {
  id: string;
  legalName: string;
  displayName: string;
  ein?: string;
  website?: string;
  headquarters: string;
  programs: string[];
  geographies: string[];
  relationshipStatus: RelationshipStatus;
  pipelineStage: string;
  ownerId: string;
  readinessStatus: ReadinessStatus;
  rationale: string;
  nextAction?: string;
  nextActionAt?: string;
  openQuestionCount: number;
  facts: Fact[];
}

export interface DiligenceCase {
  id: string;
  organizationId: string;
  type: "new_application" | "renewal" | "grant_increase" | "organization_review";
  title: string;
  requestAmount?: number;
  currency?: string;
  dueAt?: string;
  ownerId: string;
  status: "assembling" | "reviewing" | "assessment" | "memo_ready" | "complete";
  sourceIds: string[];
  signalIds: string[];
  questionIds: string[];
  assessment?: string;
}
~~~

## 13.6 Seeded data requirements

Create:

- 12 fictional organizations.
- 8 current grantees.
- 4 vetted or early prospects.
- 15 grants across three fiscal years.
- 4 applications/diligence cases.
- 40 source metadata records.
- At least 60 facts with varied evidence states.
- 12 tasks/alerts.
- 3 saved views.
- 3 watchlists.
- 2 strategy lenses.
- 6 nonprofit opportunities/grants.

Use plausible but fictional names, data, documents, people, and contact information. Display “Demo data” in the workspace switcher.

## 13.7 Required fictional organizations

Use these names so routes and screenshots remain consistent:

1. Kijani Health Collaborative
2. Coastal Learning Network
3. Open Roads Initiative
4. Andean Water Partnership
5. Sahel Women’s Enterprise Fund
6. Cedar Community Legal Center
7. Horizon Food Systems
8. Pacific Resilience Lab
9. Bright Futures Nepal
10. Local Power Cooperative
11. Community Data Trust
12. Global Midwives Alliance

The organizations should vary in scale, geography, evidence coverage, and relationship status. No fictional issue should imply real misconduct.

## 13.8 Required demo state

Kijani Health Collaborative must include:

- Latest verified operating expenses: $3.8M.
- Active grant: $450K.
- Proposed grant increase: $750K over 24 months.
- Current-grantee relationship.
- Human-set Ready to consider status.
- Kenya operating evidence.
- Uganda proposed activity with a clarification question.
- One low-confidence salary extraction initially off by one row.
- One audit/990 scope conflict.
- One current context note.

The Overview must initially show:

- 8 current partners.
- $4.2M active commitments.
- 3 renewals in 90 days.
- 5 ready-to-consider organizations.
- 7 evidence items to review.

## 13.9 Simulated operations

### Import

Advance through named steps with short delays. Let the user resolve exceptions. On completion, update counts and show a reversible summary.

### Document extraction

Show progress: Uploading → Classifying → Reading tables → Validating → Ready for review. Use deterministic fixture output.

### AI query

Support at least five preset questions and a graceful generic response for other input. Each preset response includes interpreted filters and citations.

### Memo generation

Show a short generation sequence, then open the populated editor. Changes persist.

### Evidence correction

Correcting the Kijani salary fact updates the evidence state, verifier, profile financial table, case signal, and memo preflight.

## 13.10 Reusable components

- AppShell
- SideNav
- TopBar
- WorkspaceSwitcher
- ModeSwitcher
- GlobalSearch
- AskPanel
- PageHeader
- MetricLink
- FilterBar
- SavedViewMenu
- DataTable
- OrganizationCell
- RelationshipBadge
- EvidenceBadge
- ReadinessBadge
- SourceToken
- EvidenceDrawer
- TableReviewer
- FactRow
- CapacityEvidenceProfile
- SignalCard
- QuestionCard
- Timeline
- PipelineBoard
- PipelineCard
- ChartCard
- QueryInterpretation
- ComparisonTray
- ImportWizard
- ProcessingStepper
- MemoEditor
- PreflightPanel
- EmailExtractionDrawer
- EmptyState
- ErrorState
- Toast

## 13.11 Interaction quality

- All visible buttons either perform an action, open a clearly labeled prototype message, or are intentionally disabled with an explanation.
- Charts have tooltips, keyboard-accessible summaries, and click-to-filter behavior.
- Drawers can close with Escape and return focus.
- Tables are usable by keyboard.
- Filters update counts immediately.
- URL state captures major route filters where practical.
- Status changes show a toast and update related views.
- The reset-demo action restores fixtures.
- Animations are brief and respect reduced-motion settings.

## 13.12 Responsive behavior

The primary target is 1366–1600px desktop. At 1024px, the left nav may collapse and right rails become drawers. Below 768px:

- Navigation becomes a drawer.
- Cards stack.
- Dense tables use a deliberate horizontal-scroll container.
- Three-panel diligence becomes one panel plus source/section drawers.
- No content is clipped, though full document review remains desktop-optimized.

## 13.13 Accessibility

- WCAG 2.2 AA color contrast.
- Visible focus.
- Semantic headings and landmarks.
- Labels for icon-only controls.
- Table headers and accessible captions.
- Charts paired with text summaries or data tables.
- Color-independent state labels.
- Form errors tied to fields.
- Dialog and drawer focus management.
- Reduced-motion support.

## 13.14 Content requirements

- Use the language patterns in this specification.
- Use realistic dates, amounts, tags, and source titles.
- Clearly label demo and simulated data.
- Preserve uncertainty in every summary.
- Keep AI attribution restrained.
- Do not claim impact, fraud, or funding suitability.

## 13.15 Tests

At minimum, automate:

1. Relationship/discovery overview toggle.
2. Organization filters and row navigation.
3. Evidence correction updates all dependent state.
4. Pipeline status change persists.
5. Readiness scenario totals calculate correctly.
6. Natural-language preset query shows interpreted filters.
7. Import wizard resolves exceptions and completes.
8. Nonprofit email extraction changes the stored deadline.
9. Memo preflight reflects resolved and unresolved items.
10. Reset demo restores initial state.

# 14. Acceptance script and definition of done

## 14.1 Scenario 1: relationship-led morning review

1. Open /overview.
2. Confirm the relationship-led lens and seeded metrics.
3. Click “3 renewals in 90 days.”
4. Open Kijani Health Collaborative.
5. Review “Since last review,” capacity evidence, and open questions.
6. Open the operating-expense evidence and inspect its citations.

**Pass:** Navigation and filters are clear; every displayed fact has a usable provenance path.

## 14.2 Scenario 2: correct a fragile financial extraction

1. Open Kijani Financials or the grant-increase diligence case.
2. Open the salary item marked Needs review.
3. Expand the Table Reviewer.
4. Select the correct source row.
5. Correct and verify the amount.
6. Return to the case and memo preflight.

**Pass:** The source highlight, reason for review, correction, verifier, dependent views, and audit state all update coherently.

## 14.3 Scenario 3: prepare future-giving discussion

1. Open /readiness.
2. Set $5M over 18 months for current partners and vetted prospects.
3. Filter to organizations with no critical missing source.
4. Expand two capacity evidence profiles.
5. Add exploratory discussion amounts.
6. Save the scenario and assign one research task.

**Pass:** Totals and ratios work; incomplete evidence remains visible; no allocation or recommendation is generated.

## 14.4 Scenario 4: discovery-led research

1. Toggle to Discover mode.
2. Open /landscape.
3. Run the seeded natural-language query.
4. Inspect the interpreted filters and unknown-data handling.
5. Compare two organizations.
6. Add one to a watchlist with a rationale and revisit date.

**Pass:** Criteria and source coverage are transparent; saved relationship context appears in Pipeline and Organizations.

## 14.5 Scenario 5: automatic nonprofit administration

1. Open /nonprofit.
2. Review upcoming deadlines.
3. Open the email extraction from Northstar Community Fund.
4. Compare current and proposed deadline.
5. Confirm the update.
6. Check the calendar and grant record.

**Pass:** The update is source-linked, requires confirmation, changes both views, and preserves change history.

## 14.6 Definition of done

- All P0 routes render and direct-link correctly.
- The five scenarios can be completed without developer explanation.
- Seeded data is internally consistent.
- Every major visible control has working behavior.
- Evidence and staff judgment are visibly distinct.
- No opaque score or automated funding recommendation appears.
- Loading, empty, sparse-data, and at least one error state are implemented.
- Desktop layout is polished at 1440px and usable at 1024px.
- Mobile fallback does not clip content.
- Automated tests pass.
- TypeScript and lint checks pass.
- README includes setup, commands, architecture, demo reset, and prototype limitations.

# 15. Delivery roadmap and product validation

## 15.1 Prototype validation

Test the prototype with at least:

- One relationship-rich family foundation.
- One discovery-led or newer foundation.
- One mid-sized foundation with grants operations staff.
- One larger or multi-program funder.
- Two nonprofit operations/development users.

Use task-based sessions rather than feature tours. Ask users to prepare a diligence view, reconstruct a pipeline decision, respond to a future-giving scenario, and confirm an extracted deadline.

## 15.2 Recommended pilot

A strong first pilot for a relationship-rich foundation would:

1. Import current grantees and the existing vetted pipeline.
2. Resolve identity and relationship history.
3. Process a small set of recent 990s, audits, budgets, proposals, and reports.
4. Complete five to ten real diligence or renewal cases.
5. Build the first future-readiness pool.
6. Produce one board or staff packet.
7. Measure correction time, memo preparation time, source coverage, and staff trust.

For a foundation with a list similar to Jackson’s 46 vetted organizations, the pilot should prioritize making that list living and decision-ready rather than adding more sourcing volume.

## 15.3 Production phases

### Phase 1: evidence and relationship MVP

- File imports and entity resolution.
- Organization profiles.
- Public filing enrichment.
- Core document extraction and verification.
- Diligence cases and memo export.
- Pipeline and portfolio.
- Tasks and basic reminders.

### Phase 2: monitoring and readiness

- Scheduled filing/web updates.
- Stronger “since last review.”
- Readiness scenarios.
- Email-derived dates.
- Saved alerts.
- Direct GMS connector pilots.

### Phase 3: landscape intelligence

- Broader data coverage.
- Strategy lenses.
- Natural-language query planning.
- Map and comparison.
- Licensed/curated source entitlements.

### Parallel product experiment: Nonprofit Grant Hub

- Email-to-record workflow.
- Calendar and reporting obligations.
- Reusable organization data.
- Explicit sharing packages.

Treat the nonprofit companion as a separately validated product experiment until its buyer, distribution, and data-sharing value are clear.

## 15.4 Product validation questions

- Which user owns the product and budget inside a foundation?
- Is diligence, portfolio readiness, or discovery the strongest paid entry point by segment?
- What minimum public-data coverage is credible?
- Which facts require human verification in every case?
- How much configuration can a small foundation tolerate?
- Does “Ready to consider” accurately describe the human decision state?
- Which board and staff memo formats recur?
- How should local organizations with sparse public data be represented fairly?
- Which GMS exports are consistently available?
- Will foundations permit mailbox integration, or is forwarding sufficient?
- Does the nonprofit Grant Hub improve data quality or distribution enough to justify a second surface?

# 16. Open decisions

| Decision | Why it matters | Recommended working assumption |
|---|---|---|
| Initial ideal customer profile | Determines workflow depth and sales narrative | Relationship-rich small/mid-sized foundations with repeat diligence |
| Product naming | “Match” may imply automated matching or recommendations | Keep Match Grant brand; subtitle with “Philanthropic Intelligence” and avoid match-score language |
| Readiness terminology | “Absorptive capacity” can sound reductive | Use Capacity Evidence Profile + human-set Ready to consider |
| Public organization core | Improves scale but requires governance and licensing clarity | Architect for it; keep first pilots tenant-contained if necessary |
| Discovery data coverage | Determines credibility of landscape claims | Display coverage explicitly; never claim completeness |
| Context sources | Quality and liability vary | Use an approved, configurable, dated source set |
| Nonprofit workspace | Could expand value or dilute the foundation wedge | Prototype one flow; validate and roadmap separately |
| GMS connectors | High integration cost and fragmented market | Begin with imports; select connectors after pilot evidence |
| Document extraction provider | Accuracy varies by document type | Maintain an adapter and evaluate on the product’s own test set |
| Board access | Simplifies sharing but raises permission needs | Read-only, case-specific access in production |
| Cross-foundation intelligence | Potentially valuable and highly sensitive | No private cross-tenant sharing; consider aggregate/public products separately |

# Appendix A. Demo data matrix

| Organization | Relationship | Primary theme | Geography | Readiness | Evidence condition |
|---|---|---|---|---|---|
| Kijani Health Collaborative | Current grantee | Community health | Kenya, proposed Uganda | Ready to consider | One table review and one scope conflict |
| Coastal Learning Network | Current grantee | Education | U.S. Gulf Coast | Monitor | Current and well-supported |
| Open Roads Initiative | Vetted prospect | Rural mobility | Guatemala | Research needed | Missing current audit |
| Andean Water Partnership | Current grantee | Water systems | Peru, Ecuador | Ready to consider | Strong delivery evidence |
| Sahel Women’s Enterprise Fund | Vetted prospect | Women’s enterprise | Senegal, Mali | Monitor | Geography current; financial period stale |
| Cedar Community Legal Center | Current grantee | Legal aid | United States | Ready to consider | Revenue concentration question |
| Horizon Food Systems | Former grantee | Food security | Kenya, Tanzania | Research needed | Relationship notes stale |
| Pacific Resilience Lab | Current grantee | Climate resilience | Pacific Islands | Ready to consider | Multi-currency budget |
| Bright Futures Nepal | Early prospect | Education | Nepal | Research needed | Sparse public evidence |
| Local Power Cooperative | Current grantee | Community energy | United States | Monitor | Current filing newly received |
| Community Data Trust | Vetted prospect | Data rights | Global | Ready to consider | Executable opportunity unclear |
| Global Midwives Alliance | Current grantee | Maternal health | East Africa | Monitor | Schedule F comparison needed |

# Appendix B. Seeded natural-language queries

1. “Show vetted organizations working on maternal health in East Africa with current financial evidence.”
2. “Which current partners have renewals in the next 90 days and unresolved document gaps?”
3. “Compare operating expenses, active grants, and geography evidence for Kijani Health Collaborative and Global Midwives Alliance.”
4. “What changed across the portfolio since the last board meeting?”
5. “Find organizations similar to Andean Water Partnership by program and geography, and explain the matching attributes.”

Each response must show its interpreted scope, result count, unknown-data count, and citations.

# Appendix C. Memo outline

## Grant increase review

1. Decision context
2. Request at a glance
3. Organization and relationship
4. Financial position
5. Proposed budget and use of funds
6. Geographic and operating evidence
7. Capacity evidence profile
8. Contextual considerations
9. Open questions
10. Staff assessment
11. Staff recommendation/decision
12. Source appendix

Factual sections may be drafted. Staff assessment and recommendation/decision remain human-owned.