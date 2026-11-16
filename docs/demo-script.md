# Demo video script (about 3 minutes)

Record the screen at 1080p with the stack running and the data seeded. Speak slowly; show, then say.
Keep a second browser profile (or a private window) for the second user.

**Before recording:** `down` and `up` with a fresh seed, close other windows, set the browser zoom to
110 %, sign out. Have a term sheet PDF ready (a Final Terms from an issuer's public website).

| Time | Show | Say (in your own words) |
|---|---|---|
| 0:00 | Sign-in page | "This is Deal Copilot, a tool for DCM and syndicate teams working on bond new issues. I built it to show how a primary markets workflow, an order book and an AI assistant fit together, with the controls a bank needs." |
| 0:15 | Sign in as the syndicate user, the pipeline | "Each deal moves through eight stages from mandate to booking. The cards show blocking tasks, so the desk sees what stops a launch." |
| 0:35 | Open the deal in Book building, the stepper and the Checklist tab | "Every stage has tasks with owners and dependencies. I can only advance when the blocking ones are done." |
| 0:55 | Order book tab: ladder, buckets, anomalies | "Demand by spread level, by investor type and region. The system flags suspicious orders, such as duplicates or unusually large tickets, and excludes them." |
| 1:20 | Allocation tab: propose | "The allocation engine is plain code, so the result is exact and repeatable. The model only explains it, and its text is accepted only if the numbers match." |
| 1:40 | Switch to the approver window: approve | "Four-eyes control: the person who proposed cannot approve. The approver does, and both actions are recorded." |
| 2:00 | Investors tab: network and target list | "Which investors are in this book, and which we should call next, each with the reasons for the score." |
| 2:15 | Term sheets: upload the PDF, show Read by and the checks | "Fixed rules read what has a clear pattern in six languages. The model is called only for fields the rules missed, and I can see which one read what. Then the terms are checked against the deal." |
| 2:35 | Copilot: "What is left before launch?" then the Evidence panel | "The assistant answers only from the deal's data and the process playbook, cites its sources, and says so when it does not know." |
| 2:50 | Reports, then Admin as the admin (roles table, audit) | "Management sees the pipeline and books. The administrator sees who has which role, and the audit trail records every change and every AI answer." |
| 3:05 | Architecture picture (docs/images/architecture.png) | "Next.js, FastAPI, Neo4j and a local model through Ollama. It runs on Docker Compose and Kubernetes. All data is synthetic, and I built it with AI assistance." |

**Tips.** Rehearse once without recording. Do not read the screen aloud. If the model is slow, cut
that moment in editing. Upload to YouTube as *unlisted* and put the link in the README and on your
CV. Say plainly that the data is synthetic and that you used AI assistance; interviewers value that.
