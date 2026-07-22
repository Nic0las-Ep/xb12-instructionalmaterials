# Challenge Overview: Instructional Materials Cost Reporting Automation — AI-driven capture and routing of course textbook cost data

## Hey Just added this

## Project Objectives
- Automate capture of instructional materials cost data at the point a faculty member is assigned a section, eliminating manual survey-and-spreadsheet workflows.
- Enable a single data entry point that routes information to the course schedule, the bookstore, and state compliance/MIS reporting (XB12, zero-cost, low-cost marking).
- Improve the faculty experience by minimizing required inputs and reducing error, and improve the student experience by surfacing cost information before registration opens.
- Reduce manual data entry, error rates, and reporting lag across hundreds of sections per term, with a target of cost data available before registration.
- Leave architecture room for equity-metric correlation and system-wide course comparability analysis; platform-agnostic to scale across 116 colleges.

## Current Workflow
- Data lives across disconnected systems: course schedule, bookstore (often privately owned), and the SIS/ERP (Banner, Colleague, PeopleSoft, Workday) with state MIS reporting.
- One staff member sends a survey each term; faculty self-report book and cost details to the best of their knowledge.
- Faculty separately submit book requisitions to the bookstore; the two processes are not connected.
- Manual artifacts: per-college surveys and hand-aggregated Excel spreadsheets used to consolidate and re-key data.
- Legacy/constrained tooling: multiple SIS/ERP platforms across colleges; no single source of truth; unclear ownership of the data task.

## Key Pain Points
- No single source of truth; data is re-entered manually into three separate destinations (schedule, bookstore, MIS reporting).
- Correctly classifying materials (OER vs. free-but-not-OER, zero vs. low cost, XB12 code) requires tribal knowledge faculty often lack.
- Time cost of surveying faculty, chasing accurate responses, and manually solving classification "Tetris" section by section.
- High volume — hundreds of sections per college, four quarters per year — that is plausibly self-served/automatable.
- Platform fragmentation and disconnected, privately owned bookstore systems make integration hard; cost data is unavailable before registration (first failure point).

## Ideal Solution Vision
- A simple AI chatbot/form interface where faculty enter minimal attributes; back-end logic determines the correct classification, addressing faculty misclassification and manual routing pain points.
- Example: Faculty is presented with their name, class, and section number, then answers whether a textbook is used, ISBN if commercial, or source/access if OER; the system derives the XB12 code and zero/low-cost marking, and pushes book info to the bookstore.
- Knowledge-source strategy: match materials against OER repositories (LibreText, OpenStax, Pressbooks) — covering ~90% of cases — with Google-search verification for open status; cite source links.
- Optional surface: pre-populate returning-course data ("you used this textbook last term — same again?") to reduce entry and error, since section numbers do not roll over.
- Extension path: platform-agnostic central collection point pushing to three destinations; grow into equity/success-metric correlation and system-wide course comparability analysis without a rewrite.

## Data Availability
- Primary source of truth: De Anza offered as pilot — sample survey and raw manually aggregated data for 2–3 quarters can be provided (subject to college data-protection review).
- Supplementary datasets: OER repository sources (LibreText, OpenStax, Pressbooks) for name/open-status matching; equity/IR data via Precision Campus (De Anza).
- Human resources: pilot college contacts as demo partner; an IR SME at another college (open-source dashboard work) available for a technical follow-up on connecting course/student data.
- Known gaps: no direct SIS/ERP (Banner) access for participants — integration must be faked/mocked; no single OER repository or API; course-comparability identifiers not currently connected to this cost data.
