# RAG baseline manual review sheet

Cases follow the order in [rag_human_labels.csv](../evals/rag_human_labels.csv). Questions, expected statuses, required facts, qualifications, and unsupported parts come from [rag_cases.json](../evals/rag_cases.json). Actual answers and cited excerpts come from [rag_baseline.json](rag_baseline.json). Labels are draft; the baseline is provisional.

Each actual answer reproduces the full `generation.answer` object without changing its values. Excerpts reproduce the exact saved source text, including line breaks and tabs, for every source ID cited in that answer. Source IDs are local to each case; repeated citations share one excerpt per case. Completeness, Faithfulness, and Reason are intentionally blank; existing CSV scores are not copied.

## R01

**Question**

До якого числа треба використати перенесену відпустку за контрактом A?

**Expected status:** `answered`

**Required facts**

- **deadline**: Approved carry-over must be used by 31 March of the following year.

  - Qualification: Applies to carried days under Contract A, not current-year accrual.

**Actual `generation.answer`**

```json
{
  "status": "answered",
  "claims": [
    {
      "text": "Перенесену відпустку за контрактом A можна використати до 31 березня.",
      "source_ids": [
        "S1",
        "S2"
      ]
    }
  ],
  "missing_information": null
}
```

**Exact cited excerpts**

### R01 / S1

**Document:** Employee FAQ  
**Section:** Employee FAQ > Which annual leave balance applies?  
**Version:** 2.0  
**Source:** `data/documents/faq/F01.md`  
**Chunk ID:** `F01-9e534a93237a375af6ca2eb68dab4f1e8f7190eb7a671050e065d60664450390`  
**Cited by claim(s):** 1

```text
Which annual leave balance applies?

Contract A grants 25 days, B 15 days, and C 28 days per calendar year. Your available balance reflects monthly accrual and existing reservations. Contract B's entitlement is already part-time. Up to five approved carry-over days can be used until 31 March.
```

### R01 / S2

**Document:** Full-Time Employment Contract A  
**Section:** Full-Time Employment Contract A > 4 Leave and sickness  
**Version:** 2.0  
**Source:** `data/documents/contracts/C01.docx`  
**Chunk ID:** `C01-d8f3fa0636d02219f47289e9d71105fc2154b1b5acb2f4104c45420d59330910`  
**Cited by claim(s):** 1

```text
4 Leave and sickness

The Employee is entitled to 25 days per calendar year of annual leave and 10 days per calendar year of paid sick leave. Annual leave accrues in equal monthly portions; pending requests reserve the available balance. Only scheduled missed workdays consume either allowance.

Up to five unused annual leave days may carry over if approved by 15 December and must be used by 31 March. Sick leave does not carry over. The first three consecutive scheduled sick workdays may be self-certified; evidence is required from the fourth. The Annual Leave Policy and Sick Pay & Absence Policy govern administration.
```

**Manual review**

| Completeness | Faithfulness | Reason |
| --- | --- | --- |
|  |  |  |

## R04

**Question**

In PeopleFlow v1.8, who adjusted an attendance record and when did the employee check the result?

**Expected status:** `answered`

**Required facts**

- **actor**: The manager directly adjusted the attendance record in v1.8.

  - Qualification: Historical workflow, not the v2.0 employee request flow.

- **check**: The employee reopened the timeline after the next five-minute calculation cycle.

  - Qualification: After the manager saved the adjustment.

**Actual `generation.answer`**

```json
{
  "status": "answered",
  "claims": [
    {
      "text": "In PeopleFlow v1.8, the manager adjusted an attendance record.",
      "source_ids": [
        "S2"
      ]
    },
    {
      "text": "The employee checked the result after the next five-minute calculation cycle.",
      "source_ids": [
        "S2"
      ]
    }
  ],
  "missing_information": null
}
```

**Exact cited excerpts**

### R04 / S2

**Document:** Attendance Correction Guide v1  
**Section:** Attendance Correction Guide v1 > Manager-mediated correction  
**Version:** 1.8  
**Source:** `data/documents/manuals/M06.pdf`  
**Chunk ID:** `M06-22206e0d731cf4ddbb2e84553aebafbff0681bb4ef3e4749a22522bb3ca39cd4`  
**Cited by claim(s):** 1, 2

```text
Manager-mediated correction

1. The employee checked My time > Attendance and identified the affected workday.
2. The employee sent the manager the original event times, proposed times, and a factual reason through the internal attendance channel.
3. The manager opened Team > Attendance, selected the employee and date, and chose Adjust record.
4. The manager entered the replacement values, recorded the employee's reason, and saved the adjustment.
5. The employee reopened the timeline after the next five-minute calculation cycle to confirm the result.

There was no employee Submit correction button and no employee correction-request status page. An email or chat message to the manager did not itself change the attendance ledger. The manager was responsible for checking the roster and retaining the explanation in the adjustment note. Manager adjustment history stored both previous and replacement timestamps.
```

**Manual review**

| Completeness | Faithfulness | Reason |
| --- | --- | --- |
|  |  |  |

## R05

**Question**

У PeopleFlow v2.0 який строк подання виправлення обліку часу та що робити з помилкою ATT-LOCK?

**Expected status:** `answered`

**Required facts**

- **window**: Self-service is available within 14 calendar days from the affected workday.

  - Qualification: The clock starts at the affected workday; calendar days, not business days.

- **unlocked**: Self-service requires an unlocked payroll period.

  - Qualification: Being within 14 days does not override a locked payroll period.

- **locked_route**: ATT-LOCK requires HR Payroll controlled adjustment even within the 14-day window.

  - Qualification: This exception applies even within 14 days; no historical manager-edit bypass.

**Actual `generation.answer`**

```json
{
  "status": "answered",
  "claims": [
    {
      "text": "У PeopleFlow v2.0 строк подання виправлення обліку часу становить 14 календарних днів.",
      "source_ids": [
        "S1",
        "S3",
        "S4"
      ]
    },
    {
      "text": "При помилці ATT-LOCK потрібно звернутися до HR Payroll для контролюваного виправлення.",
      "source_ids": [
        "S2",
        "S3"
      ]
    }
  ],
  "missing_information": null
}
```

**Exact cited excerpts**

### R05 / S1

**Document:** PeopleFlow Release Notes v2.0  
**Section:** PeopleFlow Release Notes v2.0 > New self-service actions  
**Version:** 2.0  
**Source:** `data/documents/release_notes/F04.md`  
**Chunk ID:** `F04-053772e0634e9843d4e8becb9b1d255bda71ca64423f1f231cf347f82c060101`  
**Cited by claim(s):** 1

```text
New self-service actions

- Employees now submit correction requests from their own attendance timeline. The window is 14 calendar days and payroll must be unlocked. One pending request per workday is allowed. Managers approve or reject; approval recalculates within five minutes. HR Payroll handles locked or older periods, replacing the former direct manager-edit route.
- Employees now cancel pending or approved annual leave themselves before the first scheduled shift starts. Cancellation immediately releases the reserved or deducted balance and notifies the manager. Started leave still requires HR review. Employees no longer need to contact HR Support for every cancellation.
- Employees can propose a swap at least 24 hours before the earlier shift starts. The colleague must accept within 12 hours; the manager then approves. Until approval updates both assignments, the original roster applies. Team, skill, overlap, 11-hour rest and weekly-hour checks apply. Unaccepted proposals expire after 12 hours or at the earlier shift start, whichever comes first.
```

### R05 / S3

**Document:** Attendance Troubleshooting  
**Section:** Attendance Troubleshooting > Correction controls  
**Version:** 2.0  
**Source:** `data/documents/support/S04.md`  
**Chunk ID:** `S04-e0856f2c390a0bf231d1f12be845471c8c5ec0269a8ec51a24e38080755f1009`  
**Cited by claim(s):** 1, 2

```text
Correction controls

Since 2026-09-01, employees can submit their own attendance correction requests within 14 calendar days of the workday if payroll is unlocked. Approval remains with the manager and triggers recalculation within five minutes. ATT-409 means a pending correction already exists; withdraw it before submitting a replacement. ATT-LOCK routes to HR Payroll. A request outside the window also requires HR Payroll review. Attendance Correction Guide v1's direct manager-edit procedure is historical and must not be used to bypass these controls.
```

### R05 / S4

**Document:** Attendance Correction Guide v2  
**Section:** Attendance Correction Guide v2 > Submit a correction  
**Version:** 2.0  
**Source:** `data/documents/manuals/M07.html`  
**Chunk ID:** `M07-165c674906938d2bfc324e62cc139f7820395a744230f112a6b4ef6f2febbbab`  
**Cited by claim(s):** 1

```text
Submit a correction

1. Open My time > Attendance, select the workday, and choose Request correction.
2. Review the original timeline and enter the complete proposed timeline, including unpaid breaks.
3. Enter a reason of 20 to 500 characters explaining what happened.
4. Review the proposed worked hours and select Submit request.
5. Save the request reference and check the Pending approval status.

Self-service is available within 14 calendar days of the affected workday while the payroll period is unlocked. At most one pending correction is allowed per workday. ATT-409 identifies a competing pending request. Withdraw the existing request before proposing a different timeline. Employees may withdraw pending requests but cannot approve their own requests. Manager decisions should be made within two business days.
```

### R05 / S2

**Document:** Attendance Correction Guide v2  
**Section:** Attendance Correction Guide v2 > Outside the self-service window  
**Version:** 2.0  
**Source:** `data/documents/manuals/M07.html`  
**Chunk ID:** `M07-2caa8a2aeb3bf1ea5fbdbe798d03242d2a976ec3492599b552a83fa9ff63554e`  
**Cited by claim(s):** 2

```text
Outside the self-service window

ATT-LOCK means payroll has locked the period, even if the date falls within 14 days. ATT-422 means the proposed event sequence is invalid. Requests outside the window or in a locked period go to HR Payroll for a controlled adjustment; the employee must not alter a different workday as a workaround. A manager can review requests in Manager Approval Dashboard but cannot use the old Attendance Correction Guide v1 direct-edit procedure to bypass v2.0 controls. The original events, request, decision, and resulting ledger revision remain linked for audit.
```

**Manual review**

| Completeness | Faithfulness | Reason |
| --- | --- | --- |
|  |  |  |

## R06

**Question**

According to Leave Request Guide v1 for v1.8, how did an employee cancel approved leave and confirm the balance was released?

**Expected status:** `answered`

**Required facts**

- **contact**: Contact HR Support with the request reference, absence dates and full-cancellation intent.

  - Qualification: Historical v1.8; no employee Cancel leave control.

- **confirm**: After HR records cancellation, reopen the request to confirm Cancelled and check the released balance.

  - Qualification: The support message alone does not restore days.

**Actual `generation.answer`**

```json
{
  "status": "partial",
  "claims": [
    {
      "text": "To cancel approved leave, the employee contacted HR Support with the request reference, absence dates, and whether the entire request should be cancelled.",
      "source_ids": [
        "S1"
      ]
    },
    {
      "text": "HR checked whether leave had already started, reviewed any payroll impact, and recorded the cancellation.",
      "source_ids": [
        "S1"
      ]
    },
    {
      "text": "The employee then reopened the request to confirm Cancelled and checked the released balance.",
      "source_ids": [
        "S1"
      ]
    }
  ],
  "missing_information": "The procedure for confirming the balance was released after cancellation is not explicitly detailed in the provided excerpts."
}
```

**Exact cited excerpts**

### R06 / S1

**Document:** Leave Request Guide v1  
**Section:** Leave Request Guide v1 > Historical cancellation procedure  
**Version:** 1.8  
**Source:** `data/documents/manuals/F05.pdf`  
**Chunk ID:** `F05-a844a9b7539be10f854fc90b9e88e83ce0281e0b0cd6b74c203c7c42255f0be4`  
**Cited by claim(s):** 1, 2, 3

```text
Historical cancellation procedure

Employees had no self-service cancellation control. To cancel a pending or approved request, the employee contacted HR Support with the request reference, absence dates, and whether the entire request should be cancelled. HR checked whether leave had already started, reviewed any payroll impact, and recorded the cancellation. The employee then reopened the request to confirm Cancelled and checked the released balance. Sending the support message alone did not restore any days.
```

**Manual review**

| Completeness | Faithfulness | Reason |
| --- | --- | --- |
|  |  |  |

## R07

**Question**

За Leave Request Guide v2, чи можна частково скасувати відпустку до її початку та чи потрібне нове погодження керівника для самого скасування?

**Expected status:** `answered`

**Required facts**

- **whole**: Partial cancellation is unavailable: cancel the entire unstarted request and submit a replacement.

  - Qualification: Replacement for still-needed dates needs its own approval and may face changed availability.

- **approval**: Cancellation itself needs no new manager approval or HR Support ticket.

  - Qualification: Only before the first scheduled shift starts; distinguish replacement approval.

**Actual `generation.answer`**

```json
{
  "status": "answered",
  "claims": [
    {
      "text": "Часткове скасування відпустки до її початку не можливе: потрібно скасувати повну незапочату відпустку.",
      "source_ids": [
        "S1"
      ]
    },
    {
      "text": "Для скасування відпустки до її початку не потрібне нове погодження керівника.",
      "source_ids": [
        "S1",
        "S2",
        "S4"
      ]
    }
  ],
  "missing_information": null
}
```

**Exact cited excerpts**

### R07 / S1

**Document:** Leave Request Guide v2  
**Section:** Leave Request Guide v2 > Cancel before leave starts  
**Version:** 2.0  
**Source:** `data/documents/manuals/F06.html`  
**Chunk ID:** `F06-cbf4ce8fcbaf8bc32174326af396565bb05adbe6bd9494fd194d00dc0f29136e`  
**Cited by claim(s):** 1, 2

```text
Cancel before leave starts

Open the pending or approved request and choose Cancel leave. Review the complete cancellation, confirm it, and check the new Cancelled status. PeopleFlow immediately restores the reservation or deduction and notifies the manager. No new manager approval or HR Support ticket is required. Partial cancellation is not available: cancel the entire unstarted request and submit a replacement for the dates still needed. The replacement needs approval and may encounter changed availability.
```

### R07 / S2

**Document:** Annual Leave Request Guide  
**Section:** Annual Leave Request Guide > Status and cancellation  
**Version:** 2.0  
**Source:** `data/documents/manuals/M03.html`  
**Chunk ID:** `M03-81c54e0c088b4a97b8d5c8f997843e854233867e6e695ed58897b8e45e415fe8`  
**Cited by claim(s):** 2

```text
Status and cancellation

Draft has no approval effect. Pending waits for the assigned manager; Approved authorizes the absence; Rejected records a reason. From v2.0, employees may cancel their own pending or approved annual leave before its first scheduled shift begins. Open the request, choose Cancel leave, review the released days, and confirm. Cancellation is immediate, restores the reservation or deduction, and notifies the manager. A started absence requires HR review and cannot be cancelled through self-service.
```

### R07 / S4

**Document:** Annual Leave Policy  
**Section:** Annual Leave Policy > Approval and cancellation  
**Version:** 2.0  
**Source:** `data/documents/policies/C04.pdf`  
**Chunk ID:** `C04-ec13867a639c8d0d64fab62861f18a318dc2e1adb796c80c515fa8234212e99b`  
**Cited by claim(s):** 2

```text
Approval and cancellation

Managers assess team coverage and should decide within two business days. They must record a reason when rejecting a request. From 2026-09-01, employees can cancel pending or approved annual leave themselves before its first scheduled shift starts. Cancellation restores the appropriate balance immediately and notifies the manager. Once the absence has begun, HR must review any correction. Annual Leave Request Guide and Leave Request Guide v2 describe the active interface. Leave Request Guide v1 is historical and its support-mediated cancellation process is superseded.
```

**Manual review**

| Completeness | Faithfulness | Reason |
| --- | --- | --- |
|  |  |  |

## R11

**Question**

Коли спливає строк першої відповіді на Medium-звернення, відкрите у п’ятницю о 16:00 UTC, якщо свят немає?

**Expected status:** `answered`

**Required facts**

- **deadline**: The Medium first-response deadline is Monday at 12:00 UTC.

  - Qualification: Friday 16:00 UTC opening, no excluded holidays; first response, not resolution.

**Actual `generation.answer`**

```json
{
  "status": "answered",
  "claims": [
    {
      "text": "A Medium ticket opened Friday at 16:00 UTC receives one business hour on Friday and reaches its four-hour first-response deadline Monday at 12:00 UTC, assuming neither day is an excluded holiday.",
      "source_ids": [
        "S1"
      ]
    },
    {
      "text": "PeopleFlow's standard support hours are Monday through Friday, 09:00-17:00 UTC, excluding 1 January and 25 December. A business hour counts only inside that window.",
      "source_ids": [
        "S2"
      ]
    },
    {
      "text": "A business day contains eight support hours.",
      "source_ids": [
        "S2"
      ]
    },
    {
      "text": "The targets below concern a human first response, not a guaranteed fix or approval.",
      "source_ids": [
        "S2"
      ]
    },
    {
      "text": "Medium\tOne user cannot complete core work; workable alternatives are limited\t4 business hours\tEach business day",
      "source_ids": [
        "S2"
      ]
    }
  ],
  "missing_information": null
}
```

**Exact cited excerpts**

### R11 / S1

**Document:** Support Priority & SLA Policy  
**Section:** Support Priority & SLA Policy > Clock examples  
**Version:** 2.0  
**Source:** `data/documents/support/S02.md`  
**Chunk ID:** `S02-11691c4ea1e776d5b23b9cfdcdfe6037fca97802ef0f38c02a4fa0bf6e5e1216`  
**Cited by claim(s):** 1

```text
Clock examples

A Medium ticket opened Friday at 16:00 UTC receives one business hour on Friday and reaches its four-hour first-response deadline Monday at 12:00 UTC, assuming neither day is an excluded holiday. A High ticket opened at 18:00 UTC starts its standard response clock at the next business opening. Security reporting is available continuously, but continuous reporting is not a promise of a one-hour out-of-hours human response.
```

### R11 / S2

**Document:** Support Priority & SLA Policy  
**Section:** Support Priority & SLA Policy > Service calendar  
**Version:** 2.0  
**Source:** `data/documents/support/S02.md`  
**Chunk ID:** `S02-8fedb0eda33913bd7e55226b7eea74521dffb73f3e61cabc0f9f925a7d3e605e`  
**Cited by claim(s):** 2, 3, 4, 5

```text
Service calendar

PeopleFlow's standard support hours are Monday through Friday, 09:00-17:00 UTC, excluding 1 January and 25 December. A business hour counts only inside that window. A business day contains eight support hours. Security incidents use the continuous reporting route in Support Escalation & Security Incidents. The targets below concern a human first response, not a guaranteed fix or approval.

Priority	Qualification	First response	Update target
High	Organization-wide outage, blocked payroll run before cutoff, suspected restricted-data exposure	1 business hour	Every 2 business hours
Medium	One user cannot complete core work; workable alternatives are limited	4 business hours	Each business day
Low	Guidance, cosmetic defect, nonblocking request	2 business days	Every 3 business days
```

**Manual review**

| Completeness | Faithfulness | Reason |
| --- | --- | --- |
|  |  |  |

## N01

**Question**

What is the reimbursement limit for installing home solar panels under PeopleFlow policy?

**Expected status:** `unavailable`

**Required facts**

None specified in the case labels.

**Expected unsupported information**

- Home solar panel installation reimbursement policy and limit.

**Actual `generation.answer`**

```json
{
  "status": "unavailable",
  "claims": [],
  "missing_information": "The requested information about the reimbursement limit for installing home solar panels under PeopleFlow policy is unavailable in the accessible documents."
}
```

**Exact cited excerpts**

No excerpts cited: this answer has no claims or source IDs.

**Manual review**

| Completeness | Faithfulness | Reason |
| --- | --- | --- |
|  |  |  |

## P02

**Question**

Скільки триває блокування після невдалих паролів у PeopleFlow та який номер телефону служби підтримки виробника автентифікатора?

**Expected status:** `partial`

**Required facts**

- **duration**: Password lockout lasts 30 minutes.

  - Qualification: PeopleFlow lockout, not an MFA-code rotation period.

**Expected unsupported information**

- Authenticator vendor support telephone number.

**Actual `generation.answer`**

```json
{
  "status": "answered",
  "claims": [
    {
      "text": "Блокування триває 30 хвилин після невдалих паролів.",
      "source_ids": [
        "S1"
      ]
    },
    {
      "text": "Номер телефону служби підтримки виробника автентифікатора не вказаний у доступних документах.",
      "source_ids": [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5"
      ]
    }
  ],
  "missing_information": null
}
```

**Exact cited excerpts**

### P02 / S1

**Document:** PeopleFlow Release Notes v1.8  
**Section:** PeopleFlow Release Notes v1.8 > Features available in v1.8  
**Version:** 1.8  
**Source:** `data/documents/release_notes/F03.md`  
**Chunk ID:** `F03-3b867947354f7db800d26e4751bb880b3ec0e5e036310a6da67ba96ed79a0b63`  
**Cited by claim(s):** 1, 2

```text
Features available in v1.8

Employees could view their attendance timeline, submit annual leave requests, download published payslips, and upload employee documents. Managers could decide annual leave and overtime requests through the team dashboard. Session expiry was 30 minutes idle or 12 hours after login. Password lockout followed five failures in 15 minutes and lasted 30 minutes.
```

### P02 / S2

**Document:** Authentication Troubleshooting  
**Section:** Authentication Troubleshooting > Session recovery  
**Version:** 2.0  
**Source:** `data/documents/support/S03.html`  
**Chunk ID:** `S03-d41617c926610876273e1d21b6e692672af881b5a3d787b15c1983272752dbe0`  
**Cited by claim(s):** 2

```text
Session recovery

1. Save unsent text locally without copying confidential record contents.
2. Sign out, close other PeopleFlow tabs, and reopen the approved workspace bookmark.
3. Sign in once and verify the selected organization.
4. Repeat the action on a nonsensitive record if possible.

If a new session resolves HTTP 401, the earlier session likely expired. Sessions expire after 30 minutes idle or 12 hours from sign-in. A recurring 401 immediately after sign-in may indicate blocked first-party cookies or a stale organizational login route. Use a supported browser and permit the organization's required first-party session cookies. Do not disable browser security globally.
```

### P02 / S3

**Document:** Login & Password Reset Guide  
**Section:** Login & Password Reset Guide > Access prerequisites  
**Version:** 2.0  
**Source:** `data/documents/manuals/M01.html`  
**Chunk ID:** `M01-aa9518ba27d6b6ceb98eb39bec9b20cc20a6404ca7aaf5ea8d10a44285a1cd0e`  
**Cited by claim(s):** 2

```text
Access prerequisites

PeopleFlow requires an active organization membership and a supported browser: the current or immediately previous major Chrome, Edge, or Firefox release. Open the organization login page from the approved workspace bookmark. Account activation links expire after 48 hours. A pending invitation does not create a usable account until activation is completed. Authentication is independent of leave entitlement and payroll permissions.
```

### P02 / S4

**Document:** Support Priority & SLA Policy  
**Section:** Support Priority & SLA Policy > Service calendar  
**Version:** 2.0  
**Source:** `data/documents/support/S02.md`  
**Chunk ID:** `S02-8fedb0eda33913bd7e55226b7eea74521dffb73f3e61cabc0f9f925a7d3e605e`  
**Cited by claim(s):** 2

```text
Service calendar

PeopleFlow's standard support hours are Monday through Friday, 09:00-17:00 UTC, excluding 1 January and 25 December. A business hour counts only inside that window. A business day contains eight support hours. Security incidents use the continuous reporting route in Support Escalation & Security Incidents. The targets below concern a human first response, not a guaranteed fix or approval.

Priority	Qualification	First response	Update target
High	Organization-wide outage, blocked payroll run before cutoff, suspected restricted-data exposure	1 business hour	Every 2 business hours
Medium	One user cannot complete core work; workable alternatives are limited	4 business hours	Each business day
Low	Guidance, cosmetic defect, nonblocking request	2 business days	Every 3 business days
```

### P02 / S5

**Document:** Authentication Troubleshooting  
**Section:** Authentication Troubleshooting > MFA and lockout  
**Version:** 2.0  
**Source:** `data/documents/support/S03.html`  
**Chunk ID:** `S03-09a590ea31e9889002ef03509a1a894cfcc6101b053bca8a263803312f25148a`  
**Cited by claim(s):** 2

```text
MFA and lockout

Authenticator codes contain six digits and rotate every 30 seconds. Set automatic device time and use the next newly generated code once. Five failed password attempts within 15 minutes trigger a 30-minute lockout. Wait for the lockout to end rather than creating a series of reset requests. A password reset link lasts 20 minutes and is invalidated when a newer link is requested. AUTH-410 means the reset link has expired or been replaced.
```

**Manual review**

| Completeness | Faithfulness | Reason |
| --- | --- | --- |
|  |  |  |

## T01

**Question**

For Contract B, how many annual leave days per calendar year are agreed, and should I apply a second part-time factor?

**Expected status:** `answered`

**Required facts**

- **days**: Contract B grants 15 annual leave days per calendar year.

  - Qualification: Do not use Contract A 25 or Contract C 28 days.

- **factor**: The 15 days are already part-time and must not be reduced with a second part-time factor.

**Actual `generation.answer`**

```json
{
  "status": "answered",
  "claims": [
    {
      "text": "For Contract B, the agreed annual leave days per calendar year are 15.",
      "source_ids": [
        "S2",
        "S3",
        "S1"
      ]
    },
    {
      "text": "You should not apply a second part-time factor to Contract B's annual leave days, as they are already the agreed part-time entitlement.",
      "source_ids": [
        "S1",
        "S4"
      ]
    }
  ],
  "missing_information": null
}
```

**Exact cited excerpts**

### T01 / S2

**Document:** Part-Time Employment Contract B  
**Section:** Part-Time Employment Contract B > Schedule of agreed terms  
**Version:** 2.0  
**Source:** `data/documents/contracts/C02.docx`  
**Chunk ID:** `C02-7915f0ec1378e62589981c265f32f6e80b3e594a2eab60aa544b384e294c3f9f`  
**Cited by claim(s):** 1

```text
Schedule of agreed terms

Item	Agreed term
Employee	[PERSON]
Contract	B
Working time	24 hours/week
Normal attendance	Monday, Wednesday, and Friday, eight scheduled hours each day
Annual salary	USD 28,800.00 gross
Monthly installment	USD 2,400.00 gross
Annual leave	15 days per calendar year
Paid sick leave	5 days per calendar year
Probation	Three calendar months

[PERSON]; [PHONE]; [EMPLOYEE_ID]. Annual base salary: USD 28,800.00, paid as USD 2,400.00 gross each month.
```

### T01 / S3

**Document:** Employee FAQ  
**Section:** Employee FAQ > Which annual leave balance applies?  
**Version:** 2.0  
**Source:** `data/documents/faq/F01.md`  
**Chunk ID:** `F01-9e534a93237a375af6ca2eb68dab4f1e8f7190eb7a671050e065d60664450390`  
**Cited by claim(s):** 1

```text
Which annual leave balance applies?

Contract A grants 25 days, B 15 days, and C 28 days per calendar year. Your available balance reflects monthly accrual and existing reservations. Contract B's entitlement is already part-time. Up to five approved carry-over days can be used until 31 March.
```

### T01 / S1

**Document:** Annual Leave Policy  
**Section:** Annual Leave Policy > Entitlement and scope  
**Version:** 2.0  
**Source:** `data/documents/policies/C04.pdf`  
**Chunk ID:** `C04-f176eb8a7591c663a80950667ffdb798b2f83410b50967428f51d16879ec0fe1`  
**Cited by claim(s):** 1, 2

```text
Entitlement and scope

Contract A grants 25 annual leave days, Contract B 15, and Contract C 28 per calendar year. Contract B's 15 days are already the agreed part-time entitlement and must not be multiplied by a second part-time factor. A day means the employee's scheduled workday; a half day means half of that day's scheduled hours.
```

### T01 / S4

**Document:** Part-Time Employment Contract B  
**Section:** Part-Time Employment Contract B > Working arrangements  
**Version:** 2.0  
**Source:** `data/documents/contracts/C02.docx`  
**Chunk ID:** `C02-a3446b68a01df6be73c520c6ab91a903de384fe44d2238d7317e49ba1fafdf99`  
**Cited by claim(s):** 2

```text
Working arrangements

Unpaid breaks are outside the contracted hours. The workplace timezone in PeopleFlow determines roster and attendance boundaries. A roster change requires manager confirmation and must preserve the weekly total unless overtime is separately approved.

The annual leave and sick-pay allowances in the schedule are the agreed part-time amounts. They must not be multiplied by another part-time factor. Probation does not reduce them.
```

**Manual review**

| Completeness | Faithfulness | Reason |
| --- | --- | --- |
|  |  |  |

## N03

**Question**

У PeopleFlow v3.0 який строк самостійного виправлення обліку часу?

**Expected status:** `unavailable`

**Required facts**

None specified in the case labels.

**Expected unsupported information**

- Attendance self-service correction rule applicable to v3.0.

**Actual `generation.answer`**

```json
{
  "status": "partial",
  "claims": [
    {
      "text": "У PeopleFlow v3.0 строк самостійного виправлення обліку часу становить 14 календарних днів.",
      "source_ids": [
        "S1"
      ]
    }
  ],
  "missing_information": "Дані про версію PeopleFlow v3.0 відсутні в наданих джерелах. Відомо лише про версії v2.0 та v1.8."
}
```

**Exact cited excerpts**

### N03 / S1

**Document:** PeopleFlow Release Notes v2.0  
**Section:** PeopleFlow Release Notes v2.0 > New self-service actions  
**Version:** 2.0  
**Source:** `data/documents/release_notes/F04.md`  
**Chunk ID:** `F04-053772e0634e9843d4e8becb9b1d255bda71ca64423f1f231cf347f82c060101`  
**Cited by claim(s):** 1

```text
New self-service actions

- Employees now submit correction requests from their own attendance timeline. The window is 14 calendar days and payroll must be unlocked. One pending request per workday is allowed. Managers approve or reject; approval recalculates within five minutes. HR Payroll handles locked or older periods, replacing the former direct manager-edit route.
- Employees now cancel pending or approved annual leave themselves before the first scheduled shift starts. Cancellation immediately releases the reserved or deducted balance and notifies the manager. Started leave still requires HR review. Employees no longer need to contact HR Support for every cancellation.
- Employees can propose a swap at least 24 hours before the earlier shift starts. The colleague must accept within 12 hours; the manager then approves. Until approval updates both assignments, the original roster applies. Team, skill, overlap, 11-hour rest and weekly-hour checks apply. Unaccepted proposals expire after 12 hours or at the earlier shift start, whichever comes first.
```

**Manual review**

| Completeness | Faithfulness | Reason |
| --- | --- | --- |
|  |  |  |
