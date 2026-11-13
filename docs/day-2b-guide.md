# Day 2b guide: sign-in, roles, saved conversations and the new look

This step sits between Day 2 and Day 3. It changes how people get into the portal, how the Copilot
remembers a conversation, and how everything looks. Business logic from Days 1 and 2 is unchanged.

## 1. What changed, in one table

| Area | Before | Now |
| --- | --- | --- |
| Identity | A role dropdown that sent `X-Demo-Role` headers | Username and password, signed token, role read from the token |
| Frontend session | None | httpOnly cookie, server-side proxy adds the token, middleware redirects to `/login` |
| Copilot | One question, one answer | Saved threads, follow-up questions, "Understood as" line |
| UI | Plain pages | Navy top bar, green accent, light and dark theme, status pills, tabular numbers |
| Pipeline page | List | KPI tiles plus charts |

## 2. Authentication

**Passwords.** Hashed with scrypt from the standard library (`app/core/passwords.py`). For an unknown
username the code still verifies against a dummy hash, so response time does not reveal which
usernames exist.

**Tokens.** `app/core/tokens.py` issues HS256 JWTs (PyJWT) with `iss`, `sub`, `role`, `name`, `exp`
and `jti`. The API trusts the role in the signed token, never a role sent by the browser.

**Modes.** `AUTH_MODE=jwt` is the default. `AUTH_MODE=demo` still accepts `X-Demo-*` headers and exists
only for development and tests. In production the app refuses to start with demo mode or a missing or
weak `JWT_SECRET` (`check_safe_to_run`).

**Lockout.** Five failed logins for a username lock it for five minutes (HTTP 429). Login, failed
login and logout are written to the audit trail.

**Browser flow.**
1. `/login` posts to the Next.js route `/api/session`.
2. That route calls the API, then stores the token in an httpOnly cookie `dc_session`
   (SameSite=Lax, `Secure` when `COOKIE_SECURE` is set). JavaScript in the page cannot read it.
3. Every call goes through the Next.js `/api/...` proxy, which adds `Authorization: Bearer ...` from
   the cookie. Write requests also pass an origin check.
4. `middleware.ts` redirects to `/login` when there is no cookie. The `next` parameter is checked by
   `safeNext` so it cannot redirect to another site.
5. The page asks the server who is signed in (`SessionProvider`), so the UI never trusts its own memory.

## 3. Roles

| Role | Can do |
| --- | --- |
| viewer | Read deals, use the Copilot |
| marketer | Create and edit deals |
| syndicate | Edit deals, read and simulate the order book, propose allocations |
| approver | Read order book and allocations, approve or reject (never their own proposal) |
| admin | Read the audit trail and list users |

Hiding a menu link is a convenience only. Every route checks the role on the server
(`require_roles`), and the browser test confirms a hidden page returns 403 when called directly.

Demo users are created by the seed: `admin.user`, `anna.syndicate`, `marco.approver`, `mia.marketer`,
`vera.viewer`. The password is `DEMO_USER_PASSWORD` from `.env.dev`, or `DealCopilot-Demo-1` when empty.
These are development accounts for synthetic data. Never reuse them anywhere real.

## 4. Conversations

- `Conversation` and `Message` nodes in Neo4j, always queried by owner, so one user cannot read
  another user's thread (a foreign id returns 404).
- Ids are created by the server (32 hex characters).
- **History is read from the database, not from the browser.** A client cannot inject fake history.
- LangGraph flow is now: `rewrite -> classify -> lookup -> retrieve -> compose`. The rewrite step turns
  "and who approved it?" into a standalone question using the earlier turns. It is skipped when the
  thread has no history. The result is shown as "Understood as ..." so you can see what was asked.
- A turn is saved only after the answer succeeded, so a failed call leaves no half-turn.
- Answers still cite their sources in the Evidence panel.

Explaining it to a recruiter: "The model never sees raw client history and never decides who may do
what. The server rebuilds the context, rewrites the follow-up, and the answer is grounded in graph
data with citations."

## 5. The design system

All colours, spacing and radii are CSS tokens in `app/globals.css`. Light is the default, dark follows
the system or the toggle (`data-theme`), and the choice is remembered. Status is never colour alone:
every pill carries text. Numbers use tabular figures so columns line up. Layout works down to phone width.

## 6. How to run it

```bat
copy .env.dev.example .env.dev
docker compose -p dealcopilot-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml up --build
docker compose -p dealcopilot-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml --profile tools build seed
docker compose -p dealcopilot-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml --profile tools run --rm seed
```

Run the seed again even if you seeded before: it skips existing deals but creates the demo users.
Open http://localhost:3000 and sign in as `anna.syndicate`. Production needs a real `JWT_SECRET`
(`python -c "import secrets; print(secrets.token_urlsafe(48))"`) and `COOKIE_SECURE=true` behind HTTPS.

## 7. Try this

1. Sign in as `vera.viewer`; confirm Order book is missing from the menu, then open `/orderbook`.
2. As `anna.syndicate` propose an allocation for `D-2026-009`; sign out, sign in as `marco.approver`, approve.
3. Try to approve as `anna.syndicate`: it must be refused (four-eyes).
4. In the Copilot ask "What is left before launch?", then "Who owns the first one?". Check "Understood as".
5. Reload: the thread is in the sidebar. Rename it, start a new one.
6. Enter a wrong password five times and see the lock.

## 8. Honest limits

- A token stays valid until it expires; there is no server-side revoke list yet.
- Lockout is kept in process memory, per username, and resets when the API restarts.
- Demo accounts and the default password are for development only.
- No SSO, MFA or password reset. A bank would use its identity provider.
- A deal changed during a thread is seen from the next question.
- Failed Copilot calls are not saved.

## 9. What was tested

Automated: backend tests (auth, conversations, role checks, allocation guard) with in-memory fakes,
frontend lint, unit tests and build, and a real-browser run of 32 checks against the built frontend.
**Not yet run against real services:** the new Neo4j queries (covered by two new integration tests that
run in CI or locally with Neo4j), the real model's follow-up rewrite quality, and the full Docker seed.
Run the stack once and try section 7 before relying on it.
