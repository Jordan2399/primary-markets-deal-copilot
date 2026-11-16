# Day 3c: finishing the base application

What was added, and how to try it.

| Area | What | Where |
|---|---|---|
| Sign-in and shell | Professional sign-in, account menu, tab titles, keyboard skip link, logo | `app/login`, `components/Nav.tsx`, `components/Brand.tsx` |
| Demo notice | Shown to administrators only | `components/AdminNote.tsx` |
| Reports | KPIs, deals by stage, activity, deals and books, demand mix, CSV export, print to PDF | `app/reports`, `backend/app/reports` |
| Admin console | Users, role table, sign-ins, Copilot usage (admin only) | `app/admin`, `backend/app/admin` |
| Search | Ctrl+K from any page: pages, deals, investors (viewers get no investors) | `components/CommandPalette.tsx`, `backend/app/search` |
| Evaluation | Offline term sheet set and a Copilot question set | `backend/app/evals`, `docs/evaluation.md` |
| Docs | Architecture, demo script, Kubernetes guide, README | `docs/` |

## Try it

1. Sign in as `anna.syndicate`, open **Reports**: the six figures, the stage bars, the deals table.
   Simulate a book on a deal in Book building first, so the cover and demand mix are filled.
   Click **Download CSV** and open it in Excel. Click **Print / save as PDF**.
2. Press **Ctrl+K**, type `nord`, press Enter: the deal opens. As `mia.marketer` or `anna.syndicate`
   type an investor name and it appears; as `vera.viewer` it does not.
3. As `anna.syndicate` open `/admin`: "Only administrators may open this page". Sign in as
   `admin.user`: the yellow environment strip appears under the top bar, and the Admin and Audit
   links appear. Other users never see the strip.
4. Run `python -m app.evals termsheets` in `backend`: 49 of 49.

## Rules worth knowing

- Reports are open to every role because they show roll-ups; investor names stay on the investor pages.
- The CSV neutralises cells that start with `=`, `+`, `-` or `@`, so a deal name cannot become a
  spreadsheet formula. Each export is written to the audit trail (`report.export`).
- The role table on the admin page mirrors the API's rules (`lib/session-utils.ts`); keep both in
  step if a rule changes.
- Users cannot be created or disabled in the interface yet (planned: users in Neo4j with desks).
