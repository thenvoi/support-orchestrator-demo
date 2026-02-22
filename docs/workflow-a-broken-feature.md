# Workflow A: "The Export Button is Broken" — Customer Support Agent Demo

## Overview

A customer support agent receives a single message from a user, kicks off 3 parallel investigations using different tools, then synthesizes the results to deliver a smart, informed response.

This workflow targets **software company** support teams where the agent has access to customer data (Excel), issue tracking (GitHub), and the live product (Browser).

---

## Customer Message

> "The export-to-CSV button on my dashboard just spins and nothing downloads. My account is sarah@acme.com."

---

## Phase 1: Three Parallel Investigations

### 1. Excel — Who is this customer?

**File:** `customers.xlsx`

The agent opens the spreadsheet and looks up `sarah@acme.com`. It reads back:

| Field | Value |
|-------|-------|
| Name | Sarah Chen |
| Company | Acme Corp |
| Plan | Pro |
| Status | Active |
| Features | Dashboard, CSV Export, API Access |
| Account ID | ACM-2847 |
| Signup | 2025-06-15 |

**What the agent now knows:** Sarah is on the Pro plan, CSV export IS included in her plan, and her account is active. So this isn't a permissions issue.

---

### 2. GitHub — Is this a known bug?

**Repo:** `company/product`

The agent searches open issues for "CSV export". It finds:

> **Issue #412:** *"CSV export spinner hangs on dashboards with >500 rows"*
> Opened 2 days ago — 3 other customers reported this
> Label: `bug`, `priority: high`
> Comment from engineer: *"Root cause identified — timeout on large datasets. Fix in PR #418, deploying Thursday."*

**What the agent now knows:** This is a known bug, it specifically affects large dashboards, there's an active fix, and there's a timeline (Thursday).

---

### 3. Browser — Can we see the problem?

**Action:** Navigate to the app's dashboard page

The agent:
1. Opens the dashboard URL
2. Sees the export button in the toolbar
3. Clicks it
4. Observes: the button shows a spinner that never resolves
5. Checks the browser console → sees `TimeoutError: Export query exceeded 30s limit`

**What the agent now knows:** The issue is reproducible. The console error confirms it matches the timeout bug from GitHub issue #412.

---

## Phase 2: Synthesize and Act

Now the agent has all three results. It connects the dots:

| Question | Answer |
|----------|--------|
| Is this a plan/permissions issue? | No — Pro plan, CSV export included |
| Is this a known bug? | Yes — GitHub #412, timeout on large datasets |
| Is it reproducible? | Yes — browser confirmed spinner + timeout error |
| Is there a fix coming? | Yes — PR #418, deploying Thursday |
| Is there a workaround? | The issue mentions filtering to <500 rows works |

**Action taken:** The agent doesn't need to file a new ticket — it already exists. It drafts a response.

---

## Final Response to Customer

> "Hi Sarah, thanks for reporting this. I looked into it and here's what I found:
>
> This is a known issue (#412) that affects CSV exports on dashboards with more than 500 rows. Our engineering team has already identified the root cause and a fix is deploying this Thursday.
>
> In the meantime, a workaround: if you apply a date filter to narrow your dashboard below 500 rows, the export will work. You can do multiple filtered exports to get all your data.
>
> I'll follow up once the fix is live. Sorry for the inconvenience!"

---

## Alternate Branches

What if the parallel steps returned different results?

### Branch B — New bug (not in GitHub)

| Excel | GitHub | Browser |
|-------|--------|---------|
| Pro plan, export included | No matching issues found | Reproduced — button errors out |

**Action:** Agent files a **Linear ticket**: *"CSV export button unresponsive — reported by ACM-2847 (Pro). Reproduced in browser. Console shows TimeoutError. Affects dashboard export."*

**Response:** *"I wasn't able to find a known issue for this, so I've filed a bug report with our engineering team (CS-1042). They'll investigate. I'll keep you updated."*

### Branch C — Plan limitation

| Excel | GitHub | Browser |
|-------|--------|---------|
| **Free plan**, export NOT included | No matching issues | Button shows "Upgrade to Pro" tooltip |

**Action:** None needed — this is expected behavior.

**Response:** *"I checked your account and it looks like CSV export is available on our Pro plan. You're currently on the Free tier. Would you like me to send you details about upgrading?"*

---

## Architecture Visual

```
"Export button is broken"
         |
         |--- Excel: sarah@acme.com ---> Pro plan, export included ---+
         |                                                             |
         |--- GitHub: "CSV export" ---> Issue #412 found, fix Thu ----+---> Respond with
         |                                                             |    known bug info
         |--- Browser: try export ---> Reproduced, timeout error -----+    + workaround
         |
         |   +-------------------------------------------------------+
         |   |  Alt: no GitHub issue    -> file Linear ticket         |
         |   |  Alt: free plan          -> suggest upgrade            |
         |   +-------------------------------------------------------+
```

---

## Tools Used

| Tool | Purpose | Demo Requirement |
|------|---------|-----------------|
| **Excel (XLS/CSV)** | Customer data lookup | Create mock `customers.xlsx` |
| **GitHub Issues** | Known bug search | Use existing GitHub repo with mock issues |
| **Browser Automation** | Live reproduction | Need a web page with an export button |
| **Linear** | Bug filing (Branch B) | Linear MCP integration |

## The Pattern

Every customer issue follows the same parallel investigation shape:

1. **WHO** is this customer? → Excel (account, plan, usage)
2. **IS** this a known problem? → GitHub / Web search (bugs, outages)
3. **WHAT's** actually happening? → Browser (reproduce, verify, check live state)
4. **ACT** on combined findings → Linear ticket / Slack escalation / direct answer
