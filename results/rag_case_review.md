# PeopleFlow RAG case review — draft

Labels derived before Task 9A generation. Review facts, qualifications, source alternatives
and negative-case absence before changing suite status to reviewed.

Regex checks are lexical proxies; semantic-only facts and every qualification need review.

## R01 · answered

До якого числа треба використати перенесену відпустку за контрактом A?

Access: all_employees, hr_confidential.

- **deadline**: Approved carry-over must be used by 31 March of the following year. Qualifications: Applies to carried days under Contract A, not current-year accrual. Sources: E1, E2, E3. Check: regex.

Label note: Reused reviewed retrieval R01 question; answer facts independently derived from canonical passages. RAG labels remain draft.

**E1: Full-Time Employment Contract A / Full-Time Employment Contract A > 4 Leave and sickness (v2.0)** · `C01-d8f3fa0636d02219f47289e9d71105fc2154b1b5acb2f4104c45420d59330910`

> 4 Leave and sickness  The Employee is entitled to 25 days per calendar year of annual leave and 10 days per calendar year of paid sick leave. Annual leave accrues in equal monthly portions; pending requests reserve the available balance. Only scheduled missed workdays consume either allowance.  Up to five unused annual leave days may carry over if approved by 15 December and must be used by 31 March. Sick leave does not carry over. The first three consecutive scheduled sick workdays may be self-certified; evidence is required from the fourth. The Annual Leave Policy and Sick Pay & Absence Policy govern administration.

**E2: Employee FAQ / Employee FAQ > Which annual leave balance applies? (v2.0)** · `F01-9e534a93237a375af6ca2eb68dab4f1e8f7190eb7a671050e065d60664450390`

> Which annual leave balance applies?  Contract A grants 25 days, B 15 days, and C 28 days per calendar year. Your available balance reflects monthly accrual and existing reservations. Contract B's entitlement is already part-time. Up to five approved carry-over days can be used until 31 March.

**E3: Annual Leave Policy / Annual Leave Policy > Carry-over and scheduling (v2.0)** · `C04-d678b76c960677507dfca5b9cef0cbd40f0a3d10ea464dacb5bf1857d6c300f4`

> Carry-over and scheduling  Up to five unused days may carry into the next calendar year if a manager approves carry-over by 15 December. Carry-over expires on 31 March of the next year and is consumed before current-year accrual. The rest expires at year end. Organization holidays and nonworking roster days do not consume annual leave. Submit requests at least five calendar days before the first absence; a manager may approve shorter notice with a recorded exception reason.

## R02 · answered

Under Part-Time Employment Contract B, from which consecutive scheduled sick workday is medical evidence required?

Access: all_employees, hr_confidential.

- **evidence**: Medical evidence starts on the fourth consecutive scheduled sick workday under Contract B. Qualifications: Count consecutive scheduled sick workdays, not calendar days. Sources: E1. Check: regex.

Label note: Reused reviewed retrieval R02 question; answer facts independently derived from canonical passages. RAG labels remain draft.

**E1: Part-Time Employment Contract B / Part-Time Employment Contract B > Taking leave and reporting sickness (v2.0)** · `C02-7213775f8220c8c359d72e6b65b1afc76e92027d043bdd46c11bd2e98e13afde`

> Taking leave and reporting sickness  Annual leave accrues monthly in equal portions. Pending requests reserve balance. Scheduled workdays alone consume annual or sick leave. Up to five unused annual leave days may carry into the next year with approval by 15 December; carried days expire on 31 March. Sick leave does not carry over.  The first three consecutive scheduled sick workdays are covered by self-certification. Medical evidence is required from the fourth. The Annual Leave Policy and Sick Pay & Absence Policy apply to requests, evidence and balances.

## R03 · answered

За Annual Leave Policy, що витрачається першим: перенесені дні відпустки чи нарахування поточного року?

Access: all_employees.

- **order**: Approved carry-over is consumed before current-year accrual. Qualifications: Do not reverse the consumption order. Sources: E1. Check: semantic.

Label note: Reused reviewed retrieval R03 question; answer facts independently derived from canonical passages. RAG labels remain draft.

**E1: Annual Leave Policy / Annual Leave Policy > Carry-over and scheduling (v2.0)** · `C04-d678b76c960677507dfca5b9cef0cbd40f0a3d10ea464dacb5bf1857d6c300f4`

> Carry-over and scheduling  Up to five unused days may carry into the next calendar year if a manager approves carry-over by 15 December. Carry-over expires on 31 March of the next year and is consumed before current-year accrual. The rest expires at year end. Organization holidays and nonworking roster days do not consume annual leave. Submit requests at least five calendar days before the first absence; a manager may approve shorter notice with a recorded exception reason.

## R04 · answered

In PeopleFlow v1.8, who adjusted an attendance record and when did the employee check the result?

Access: all_employees.

- **actor**: The manager directly adjusted the attendance record in v1.8. Qualifications: Historical workflow, not the v2.0 employee request flow. Sources: E1, E2. Check: semantic.
- **check**: The employee reopened the timeline after the next five-minute calculation cycle. Qualifications: After the manager saved the adjustment. Sources: E1. Check: regex.

Label note: Reused reviewed retrieval R04 question; answer facts independently derived from canonical passages. RAG labels remain draft.

**E1: Attendance Correction Guide v1 / Attendance Correction Guide v1 > Manager-mediated correction (v1.8)** · `M06-22206e0d731cf4ddbb2e84553aebafbff0681bb4ef3e4749a22522bb3ca39cd4`

> Manager-mediated correction  1. The employee checked My time > Attendance and identified the affected workday. 2. The employee sent the manager the original event times, proposed times, and a factual reason through the internal attendance channel. 3. The manager opened Team > Attendance, selected the employee and date, and chose Adjust record. 4. The manager entered the replacement values, recorded the employee's reason, and saved the adjustment. 5. The employee reopened the timeline after the next five-minute calculation cycle to confirm the result.  There was no employee Submit correction button and no employee correction-request status page. An email or chat message to the manager did not itself change the attendance ledger. The manager was responsible for checking the roster and retaining the explanation in the adjustment note. Manager adjustment history stored both previous and replacement timestamps.

**E2: PeopleFlow Release Notes v1.8 / PeopleFlow Release Notes v1.8 > Attendance in this release (v1.8)** · `F03-0c335afe0f4dc96d185512a3b22766a0369f22c8dd32d4d053a1bf92b8a3c858`

> Attendance in this release  Employees could not submit attendance correction requests. They sent the original times, proposed times, and reason to their manager. Managers directly adjusted unlocked records within 30 calendar days; older or locked periods required HR Payroll. Attendance Correction Guide v1 contains that historical procedure.

## R05 · answered

У PeopleFlow v2.0 який строк подання виправлення обліку часу та що робити з помилкою ATT-LOCK?

Access: all_employees.

- **window**: Self-service is available within 14 calendar days from the affected workday. Qualifications: The clock starts at the affected workday; calendar days, not business days. Sources: E1, E2. Check: regex.
- **unlocked**: Self-service requires an unlocked payroll period. Qualifications: Being within 14 days does not override a locked payroll period. Sources: E1, E2, E3, E4. Check: regex.
- **locked_route**: ATT-LOCK requires HR Payroll controlled adjustment even within the 14-day window. Qualifications: This exception applies even within 14 days; no historical manager-edit bypass. Sources: E5, E2. Check: regex.

Label note: Exact Task 8 R05 smoke question without the deadline hint. Three separately required facts/qualifications derived from M07/S04; smoke answers were already seen during Task 8, not used as labels.

**E1: Attendance Correction Guide v2 / Attendance Correction Guide v2 > Submit a correction (v2.0)** · `M07-165c674906938d2bfc324e62cc139f7820395a744230f112a6b4ef6f2febbbab`

> Submit a correction  1. Open My time > Attendance, select the workday, and choose Request correction. 2. Review the original timeline and enter the complete proposed timeline, including unpaid breaks. 3. Enter a reason of 20 to 500 characters explaining what happened. 4. Review the proposed worked hours and select Submit request. 5. Save the request reference and check the Pending approval status.  Self-service is available within 14 calendar days of the affected workday while the payroll period is unlocked. At most one pending correction is allowed per workday. ATT-409 identifies a competing pending request. Withdraw the existing request before proposing a different timeline. Employees may withdraw pending requests but cannot approve their own requests. Manager decisions should be made within two business days.

**E2: Attendance Troubleshooting / Attendance Troubleshooting > Correction controls (v2.0)** · `S04-e0856f2c390a0bf231d1f12be845471c8c5ec0269a8ec51a24e38080755f1009`

> Correction controls  Since 2026-09-01, employees can submit their own attendance correction requests within 14 calendar days of the workday if payroll is unlocked. Approval remains with the manager and triggers recalculation within five minutes. ATT-409 means a pending correction already exists; withdraw it before submitting a replacement. ATT-LOCK routes to HR Payroll. A request outside the window also requires HR Payroll review. Attendance Correction Guide v1's direct manager-edit procedure is historical and must not be used to bypass these controls.

**E3: PeopleFlow Release Notes v2.0 / PeopleFlow Release Notes v2.0 > New self-service actions (v2.0)** · `F04-053772e0634e9843d4e8becb9b1d255bda71ca64423f1f231cf347f82c060101`

> New self-service actions  - Employees now submit correction requests from their own attendance timeline. The window is 14 calendar days and payroll must be unlocked. One pending request per workday is allowed. Managers approve or reject; approval recalculates within five minutes. HR Payroll handles locked or older periods, replacing the former direct manager-edit route. - Employees now cancel pending or approved annual leave themselves before the first scheduled shift starts. Cancellation immediately releases the reserved or deducted balance and notifies the manager. Started leave still requires HR review. Employees no longer need to contact HR Support for every cancellation. - Employees can propose a swap at least 24 hours before the earlier shift starts. The colleague must accept within 12 hours; the manager then approves. Until approval updates both assignments, the original roster applies. Team, skill, overlap, 11-hour rest and weekly-hour checks apply. Unaccepted proposals expire after 12 hours or at the earlier shift start, whichever comes first.

**E4: Employee FAQ / Employee FAQ > How do I fix a missing punch? (v2.0)** · `F01-ab1680ca26fcf554d67768a89e46427a8b624d90c0056eabcaa14c120ab5f537`

> How do I fix a missing punch?  Use My time > Attendance > Request correction within 14 calendar days while the payroll period is unlocked. Your manager must approve it. Recalculation runs within five minutes after approval. Locked or older records require HR Payroll review under Attendance Correction Guide v2.

**E5: Attendance Correction Guide v2 / Attendance Correction Guide v2 > Outside the self-service window (v2.0)** · `M07-2caa8a2aeb3bf1ea5fbdbe798d03242d2a976ec3492599b552a83fa9ff63554e`

> Outside the self-service window  ATT-LOCK means payroll has locked the period, even if the date falls within 14 days. ATT-422 means the proposed event sequence is invalid. Requests outside the window or in a locked period go to HR Payroll for a controlled adjustment; the employee must not alter a different workday as a workaround. A manager can review requests in Manager Approval Dashboard but cannot use the old Attendance Correction Guide v1 direct-edit procedure to bypass v2.0 controls. The original events, request, decision, and resulting ledger revision remain linked for audit.

## R06 · answered

According to Leave Request Guide v1 for v1.8, how did an employee cancel approved leave and confirm the balance was released?

Access: all_employees.

- **contact**: Contact HR Support with the request reference, absence dates and full-cancellation intent. Qualifications: Historical v1.8; no employee Cancel leave control. Sources: E1. Check: semantic.
- **confirm**: After HR records cancellation, reopen the request to confirm Cancelled and check the released balance. Qualifications: The support message alone does not restore days. Sources: E1. Check: semantic.

Label note: Reused reviewed retrieval R06 question; answer facts independently derived from canonical passages. RAG labels remain draft.

**E1: Leave Request Guide v1 / Leave Request Guide v1 > Historical cancellation procedure (v1.8)** · `F05-a844a9b7539be10f854fc90b9e88e83ce0281e0b0cd6b74c203c7c42255f0be4`

> Historical cancellation procedure  Employees had no self-service cancellation control. To cancel a pending or approved request, the employee contacted HR Support with the request reference, absence dates, and whether the entire request should be cancelled. HR checked whether leave had already started, reviewed any payroll impact, and recorded the cancellation. The employee then reopened the request to confirm Cancelled and checked the released balance. Sending the support message alone did not restore any days.

## R07 · answered

За Leave Request Guide v2, чи можна частково скасувати відпустку до її початку та чи потрібне нове погодження керівника для самого скасування?

Access: all_employees.

- **whole**: Partial cancellation is unavailable: cancel the entire unstarted request and submit a replacement. Qualifications: Replacement for still-needed dates needs its own approval and may face changed availability. Sources: E1. Check: semantic.
- **approval**: Cancellation itself needs no new manager approval or HR Support ticket. Qualifications: Only before the first scheduled shift starts; distinguish replacement approval. Sources: E1. Check: semantic.

Label note: Reused reviewed retrieval R07 question; answer facts independently derived from canonical passages. RAG labels remain draft.

**E1: Leave Request Guide v2 / Leave Request Guide v2 > Cancel before leave starts (v2.0)** · `F06-cbf4ce8fcbaf8bc32174326af396565bb05adbe6bd9494fd194d00dc0f29136e`

> Cancel before leave starts  Open the pending or approved request and choose Cancel leave. Review the complete cancellation, confirm it, and check the new Cancelled status. PeopleFlow immediately restores the reservation or deduction and notifies the manager. No new manager approval or HR Support ticket is required. Partial cancellation is not available: cancel the entire unstarted request and submit a replacement for the dates still needed. The replacement needs approval and may encounter changed availability.

## R08 · answered

For a v2.0 shift swap, how far in advance must I submit, how long does my colleague have to accept, and what minimum rest must the resulting roster preserve?

Access: all_employees.

- **advance**: Submit at least 24 hours before the earlier shift starts. Qualifications: Earlier of the two shifts, not either arbitrary shift. Sources: E1, E2, E3. Check: regex.
- **accept**: The colleague must accept within 12 hours of proposal. Qualifications: Colleague acceptance is not final manager approval. Sources: E1, E2, E3. Check: regex.
- **rest**: Preserve 11 consecutive hours of rest between shifts. Qualifications: Consecutive rest between resulting shifts. Sources: E4, E2. Check: regex.

Label note: Reused reviewed retrieval R08 question; answer facts independently derived from canonical passages. RAG labels remain draft.

**E1: Shift Schedule & Swap Guide / Shift Schedule & Swap Guide > Propose an employee swap (v2.0)** · `M08-7ab80a86f61e89f3aebb885db42f4081fce2d9d64f6c62a5a41f6c13b234f33c`

> Propose an employee swap  From 2026-09-01, employees initiate swaps in v2.0. The earlier v1.8 manager-initiated workflow is described only in PeopleFlow Release Notes v1.8.  1. Select a published shift and choose Propose swap. 2. Choose an eligible colleague's published shift and review both resulting assignments. 3. Submit at least 24 hours before the earlier of the two shift starts. 4. Wait for the colleague to accept within 12 hours of the proposal. 5. After acceptance, wait for manager approval before following the changed roster.  Acceptance by the colleague is not final authorization. The original assignments remain in force until the manager approves. A proposal expires after 12 hours without acceptance or when the earlier shift begins, whichever happens first. A withdrawn or rejected proposal does not modify either roster entry. An employee can withdraw before a manager decision.

**E2: PeopleFlow Release Notes v2.0 / PeopleFlow Release Notes v2.0 > New self-service actions (v2.0)** · `F04-053772e0634e9843d4e8becb9b1d255bda71ca64423f1f231cf347f82c060101`

> New self-service actions  - Employees now submit correction requests from their own attendance timeline. The window is 14 calendar days and payroll must be unlocked. One pending request per workday is allowed. Managers approve or reject; approval recalculates within five minutes. HR Payroll handles locked or older periods, replacing the former direct manager-edit route. - Employees now cancel pending or approved annual leave themselves before the first scheduled shift starts. Cancellation immediately releases the reserved or deducted balance and notifies the manager. Started leave still requires HR review. Employees no longer need to contact HR Support for every cancellation. - Employees can propose a swap at least 24 hours before the earlier shift starts. The colleague must accept within 12 hours; the manager then approves. Until approval updates both assignments, the original roster applies. Team, skill, overlap, 11-hour rest and weekly-hour checks apply. Unaccepted proposals expire after 12 hours or at the earlier shift start, whichever comes first.

**E3: Employee FAQ / Employee FAQ > Can I arrange a shift swap? (v2.0)** · `F01-e5c973bac47fd35cfdaa1c8714ec85f4a86f578d156bbe0cfc1e93ac5c11319f`

> Can I arrange a shift swap?  Employees initiate swaps in v2.0 at least 24 hours before the earlier shift begins. The colleague must accept within 12 hours, then the manager must approve. Until approval, follow the original roster. Both employees must meet the team, skill, rest and weekly-hour checks.

**E4: Shift Schedule & Swap Guide / Shift Schedule & Swap Guide > Eligibility controls (v2.0)** · `M08-f126decb86737cdf531552e994a4c19cb20d395250c49af4acf9a965bca7f096`

> Eligibility controls  Both employees must belong to the same scheduling team, hold the required shift skill tags, and have no overlapping assignment. The resulting schedule must preserve 11 consecutive hours of rest between shifts and stay within each employee's contracted weekly hours unless separately approved overtime exists. SHIFT-422 identifies a failed eligibility rule; SHIFT-409 identifies a shift already involved in a pending swap. Resolve the active proposal rather than creating duplicates.

## R09 · answered

У Payslip & Payroll Portal Guide що означає статус платежу Submitted і скільки чекати після дати виплати перед повідомленням про затримку?

Access: all_employees, hr_payroll.

- **submitted**: Submitted means the payment export was sent, not that funds settled. Sources: E1. Check: semantic.
- **wait**: Allow two business days after the stated pay date before reporting a settlement delay. Qualifications: Except when the destination is visibly incorrect; not two calendar days. Sources: E1. Check: regex.

Label note: Reused reviewed retrieval R09 question; answer facts independently derived from canonical passages. RAG labels remain draft.

**E1: Payslip & Payroll Portal Guide / Payslip & Payroll Portal Guide > Gross pay and net pay (v2.0)** · `M09-93bcd7c466126c564e1b9e94d8d0d83c5109350ab38b90812949ff2c35e728ef`

> Gross pay and net pay  Gross pay is the sum of base pay and eligible earnings. Net pay equals gross pay minus the displayed deductions; reimbursement lines are shown separately if the organization enables them. A payment marked Submitted confirms that the export was sent, not that funds settled. Allow two business days after the stated pay date before reporting a settlement delay, unless the destination is visibly incorrect.

## R10 · answered

According to Payroll Troubleshooting, when should an allowance approved after cutoff appear, and who reviews a pre-cutoff approval missing from a Published statement?

Access: all_employees, hr_payroll.

- **late**: Approval after cutoff normally appears in the following month adjustment run. Qualifications: Normally; do not promise the same payroll run. Sources: E1. Check: semantic.
- **review**: A pre-cutoff approval missing from a Published statement needs Payroll Operations review. Qualifications: Do not add the allowance manually or change the approval timestamp. Sources: E1. Check: semantic.

Label note: Reused reviewed retrieval R10 question; answer facts independently derived from canonical passages. RAG labels remain draft.

**E1: Payroll Troubleshooting / Payroll Troubleshooting > Missing allowance procedure (v2.0)** · `S05-1e43f76447840722f7b41b501b973da48368a0fab74a8ee423a9b876a81f4b05`

> Missing allowance procedure  1. Open the affected period in Pay > Payslips and check the revision number. 2. Compare the allowance approval timestamp with the cutoff. 3. Check the allowance's effective dates and whether the attendance condition was satisfied. 4. Submit Pay > Report discrepancy with the approval reference and disputed line.  An approval after cutoff normally appears in the following month's adjustment run. An approval before cutoff that is missing from a Published statement needs Payroll Operations review. Support should not add an allowance manually or change an approval timestamp to force inclusion. PAY-404 means no statement is published; PAY-403 means access is denied rather than a calculation failure.

## R11 · answered

Коли спливає строк першої відповіді на Medium-звернення, відкрите у п’ятницю о 16:00 UTC, якщо свят немає?

Access: all_employees.

- **deadline**: The Medium first-response deadline is Monday at 12:00 UTC. Qualifications: Friday 16:00 UTC opening, no excluded holidays; first response, not resolution. Sources: E1. Check: regex.

Label note: Reused reviewed retrieval R11 question; answer facts independently derived from canonical passages. RAG labels remain draft.

**E1: Support Priority & SLA Policy / Support Priority & SLA Policy > Clock examples (v2.0)** · `S02-11691c4ea1e776d5b23b9cfdcdfe6037fca97802ef0f38c02a4fa0bf6e5e1216`

> Clock examples  A Medium ticket opened Friday at 16:00 UTC receives one business hour on Friday and reaches its four-hour first-response deadline Monday at 12:00 UTC, assuming neither day is an excluded holiday. A High ticket opened at 18:00 UTC starts its standard response clock at the next business opening. Security reporting is available continuously, but continuous reporting is not a promise of a one-hour out-of-hours human response.

## R12 · answered

In Authentication Troubleshooting, how many failed password attempts trigger lockout, over what time window, and how long does the lockout last?

Access: all_employees.

- **attempts**: Five failed password attempts trigger lockout. Qualifications: Password attempts, not authenticator refreshes. Sources: E1, E2. Check: regex.
- **window**: The failed-attempt window is 15 minutes. Sources: E1, E2. Check: regex.
- **duration**: The lockout lasts 30 minutes. Sources: E1, E2. Check: regex.

Label note: Reused reviewed retrieval R12 question; answer facts independently derived from canonical passages. RAG labels remain draft.

**E1: Authentication Troubleshooting / Authentication Troubleshooting > MFA and lockout (v2.0)** · `S03-09a590ea31e9889002ef03509a1a894cfcc6101b053bca8a263803312f25148a`

> MFA and lockout  Authenticator codes contain six digits and rotate every 30 seconds. Set automatic device time and use the next newly generated code once. Five failed password attempts within 15 minutes trigger a 30-minute lockout. Wait for the lockout to end rather than creating a series of reset requests. A password reset link lasts 20 minutes and is invalidated when a newer link is requested. AUTH-410 means the reset link has expired or been replaced.

**E2: Login & Password Reset Guide / Login & Password Reset Guide > Sign in and MFA (v2.0)** · `M01-29aafeea116992f0f05e604de2eea1a6d59d904730d2e75c8d4fa9d4114bb0ea`

> Sign in and MFA  1. Select your organization, enter your work login, and choose Continue. 2. Enter your password. Passwords require at least 14 characters and cannot match the previous five passwords. 3. Enter the six-digit code from the enrolled authenticator. A code rotates every 30 seconds; set the device clock to automatic if codes are rejected. 4. Confirm the workspace name on the landing page before opening HR records.  Five failed password attempts within 15 minutes cause a 30-minute lockout. Additional attempts during the lockout do not shorten it. Sessions expire after 30 minutes of inactivity or 12 hours after sign-in, whichever comes first. Unsaved forms are not automatically submitted when a session expires.

## N01 · unavailable

What is the reimbursement limit for installing home solar panels under PeopleFlow policy?

Access: all_employees.

- **Must identify as unavailable:** Home solar panel installation reimbursement policy and limit.

Label note: Exact Task 8 absent-answer smoke question. Full canonical corpus inspected; no solar installation reimbursement rule. No invented positive evidence.

No positive evidence is labeled. Confirm absence across the canonical corpus,
not only among retrieved excerpts.

## N02 · unavailable

Який розмір компенсації витрат на дитячий садок передбачено PeopleFlow?

Access: all_employees.

- **Must identify as unavailable:** Childcare/nursery reimbursement eligibility and amount.

Label note: Corpus has HR benefits and leave policies but no childcare/nursery reimbursement policy; absence needs reviewer confirmation.

No positive evidence is labeled. Confirm absence across the canonical corpus,
not only among retrieved excerpts.

## P01 · partial

In PeopleFlow v2.0, what is the attendance correction self-service window, and what is the home solar installation reimbursement limit?

Access: all_employees.

- **window**: Self-service is available within 14 calendar days from the affected workday. Qualifications: Calendar days counted from the affected workday. Sources: E1, E2. Check: regex.
- **unlocked**: Self-service requires an unlocked payroll period. Sources: E1, E2, E3, E4. Check: semantic.
- **Must identify as unavailable:** Home solar panel installation reimbursement limit.

Label note: Known correction rule plus an absent benefit; must answer the supported part and identify the absent part.

**E1: Attendance Correction Guide v2 / Attendance Correction Guide v2 > Submit a correction (v2.0)** · `M07-165c674906938d2bfc324e62cc139f7820395a744230f112a6b4ef6f2febbbab`

> Submit a correction  1. Open My time > Attendance, select the workday, and choose Request correction. 2. Review the original timeline and enter the complete proposed timeline, including unpaid breaks. 3. Enter a reason of 20 to 500 characters explaining what happened. 4. Review the proposed worked hours and select Submit request. 5. Save the request reference and check the Pending approval status.  Self-service is available within 14 calendar days of the affected workday while the payroll period is unlocked. At most one pending correction is allowed per workday. ATT-409 identifies a competing pending request. Withdraw the existing request before proposing a different timeline. Employees may withdraw pending requests but cannot approve their own requests. Manager decisions should be made within two business days.

**E2: Attendance Troubleshooting / Attendance Troubleshooting > Correction controls (v2.0)** · `S04-e0856f2c390a0bf231d1f12be845471c8c5ec0269a8ec51a24e38080755f1009`

> Correction controls  Since 2026-09-01, employees can submit their own attendance correction requests within 14 calendar days of the workday if payroll is unlocked. Approval remains with the manager and triggers recalculation within five minutes. ATT-409 means a pending correction already exists; withdraw it before submitting a replacement. ATT-LOCK routes to HR Payroll. A request outside the window also requires HR Payroll review. Attendance Correction Guide v1's direct manager-edit procedure is historical and must not be used to bypass these controls.

**E3: PeopleFlow Release Notes v2.0 / PeopleFlow Release Notes v2.0 > New self-service actions (v2.0)** · `F04-053772e0634e9843d4e8becb9b1d255bda71ca64423f1f231cf347f82c060101`

> New self-service actions  - Employees now submit correction requests from their own attendance timeline. The window is 14 calendar days and payroll must be unlocked. One pending request per workday is allowed. Managers approve or reject; approval recalculates within five minutes. HR Payroll handles locked or older periods, replacing the former direct manager-edit route. - Employees now cancel pending or approved annual leave themselves before the first scheduled shift starts. Cancellation immediately releases the reserved or deducted balance and notifies the manager. Started leave still requires HR review. Employees no longer need to contact HR Support for every cancellation. - Employees can propose a swap at least 24 hours before the earlier shift starts. The colleague must accept within 12 hours; the manager then approves. Until approval updates both assignments, the original roster applies. Team, skill, overlap, 11-hour rest and weekly-hour checks apply. Unaccepted proposals expire after 12 hours or at the earlier shift start, whichever comes first.

**E4: Employee FAQ / Employee FAQ > How do I fix a missing punch? (v2.0)** · `F01-ab1680ca26fcf554d67768a89e46427a8b624d90c0056eabcaa14c120ab5f537`

> How do I fix a missing punch?  Use My time > Attendance > Request correction within 14 calendar days while the payroll period is unlocked. Your manager must approve it. Recalculation runs within five minutes after approval. Locked or older records require HR Payroll review under Attendance Correction Guide v2.

## P02 · partial

Скільки триває блокування після невдалих паролів у PeopleFlow та який номер телефону служби підтримки виробника автентифікатора?

Access: all_employees.

- **duration**: Password lockout lasts 30 minutes. Qualifications: PeopleFlow lockout, not an MFA-code rotation period. Sources: E1, E2. Check: regex.
- **Must identify as unavailable:** Authenticator vendor support telephone number.

Label note: The corpus describes lockout/MFA but does not identify an authenticator vendor support phone. Do not use synthetic employee phone fields.

**E1: Authentication Troubleshooting / Authentication Troubleshooting > MFA and lockout (v2.0)** · `S03-09a590ea31e9889002ef03509a1a894cfcc6101b053bca8a263803312f25148a`

> MFA and lockout  Authenticator codes contain six digits and rotate every 30 seconds. Set automatic device time and use the next newly generated code once. Five failed password attempts within 15 minutes trigger a 30-minute lockout. Wait for the lockout to end rather than creating a series of reset requests. A password reset link lasts 20 minutes and is invalidated when a newer link is requested. AUTH-410 means the reset link has expired or been replaced.

**E2: Login & Password Reset Guide / Login & Password Reset Guide > Sign in and MFA (v2.0)** · `M01-29aafeea116992f0f05e604de2eea1a6d59d904730d2e75c8d4fa9d4114bb0ea`

> Sign in and MFA  1. Select your organization, enter your work login, and choose Continue. 2. Enter your password. Passwords require at least 14 characters and cannot match the previous five passwords. 3. Enter the six-digit code from the enrolled authenticator. A code rotates every 30 seconds; set the device clock to automatic if codes are rejected. 4. Confirm the workspace name on the landing page before opening HR records.  Five failed password attempts within 15 minutes cause a 30-minute lockout. Additional attempts during the lockout do not shorten it. Sessions expire after 30 minutes of inactivity or 12 hours after sign-in, whichever comes first. Unsaved forms are not automatically submitted when a session expires.

## T01 · answered

For Contract B, how many annual leave days per calendar year are agreed, and should I apply a second part-time factor?

Access: all_employees, hr_confidential.

- **days**: Contract B grants 15 annual leave days per calendar year. Qualifications: Do not use Contract A 25 or Contract C 28 days. Sources: E1, E2, E3, E4. Check: regex.
- **factor**: The 15 days are already part-time and must not be reduced with a second part-time factor. Sources: E2, E3. Check: semantic.

Label note: Similar-contract trap; accept FAQ or policy when the question does not demand a contract quotation.

**E1: Part-Time Employment Contract B / Part-Time Employment Contract B > Schedule of agreed terms (v2.0)** · `C02-7915f0ec1378e62589981c265f32f6e80b3e594a2eab60aa544b384e294c3f9f`

> Schedule of agreed terms  Item	Agreed term Employee	[PERSON] Contract	B Working time	24 hours/week Normal attendance	Monday, Wednesday, and Friday, eight scheduled hours each day Annual salary	USD 28,800.00 gross Monthly installment	USD 2,400.00 gross Annual leave	15 days per calendar year Paid sick leave	5 days per calendar year Probation	Three calendar months  [PERSON]; [PHONE]; [EMPLOYEE_ID]. Annual base salary: USD 28,800.00, paid as USD 2,400.00 gross each month.

**E2: Annual Leave Policy / Annual Leave Policy > Entitlement and scope (v2.0)** · `C04-f176eb8a7591c663a80950667ffdb798b2f83410b50967428f51d16879ec0fe1`

> Entitlement and scope  Contract A grants 25 annual leave days, Contract B 15, and Contract C 28 per calendar year. Contract B's 15 days are already the agreed part-time entitlement and must not be multiplied by a second part-time factor. A day means the employee's scheduled workday; a half day means half of that day's scheduled hours.

**E3: Employee FAQ / Employee FAQ > Which annual leave balance applies? (v2.0)** · `F01-9e534a93237a375af6ca2eb68dab4f1e8f7190eb7a671050e065d60664450390`

> Which annual leave balance applies?  Contract A grants 25 days, B 15 days, and C 28 days per calendar year. Your available balance reflects monthly accrual and existing reservations. Contract B's entitlement is already part-time. Up to five approved carry-over days can be used until 31 March.

**E4: Annual Leave Request Guide / Annual Leave Request Guide > Choose the correct balance (v2.0)** · `M03-17ea89a19501c60c3e3813356b5b3a6338d423e9aba06ad0d98c82064ae9eb72`

> Choose the correct balance  Use My time > Leave to request annual leave. The assigned contract determines the annual entitlement: A provides 25 days, B provides 15 days, and C provides 28 days. A displayed available balance subtracts approved future leave and pending reservations; it is not simply the annual entitlement. See Annual Leave Policy for accrual and carry-over rules.

## T02 · answered

In PeopleFlow v1.8, what was the manager attendance adjustment window and who handled locked periods?

Access: all_employees.

- **window**: Managers could adjust unlocked records within 30 calendar days of the workday. Qualifications: Historical v1.8 manager workflow; not the current 14-day self-service rule. Sources: E1, E2. Check: regex.
- **locked**: Locked periods required HR Payroll intervention. Sources: E1, E2. Check: semantic.

Label note: Historical-version trap; superseded documents are correct evidence for an explicitly historical question.

**E1: Attendance Correction Guide v1 / Attendance Correction Guide v1 > Historical limits (v1.8)** · `M06-dcd542ceb51779f39655a708614ab59c4b00fdbebc18177be015106ee537b960`

> Historical limits  Managers could adjust unlocked records within 30 calendar days of the workday. Older records or a locked payroll period required HR Payroll intervention. The same event-order rule applied: clock-in precedes breaks and clock-out, and unpaid breaks must remain within the work interval. ATT-LOCK meant the period was locked; ATT-422 meant the proposed timeline was invalid. Saving a note alone did not clear either condition.

**E2: PeopleFlow Release Notes v1.8 / PeopleFlow Release Notes v1.8 > Attendance in this release (v1.8)** · `F03-0c335afe0f4dc96d185512a3b22766a0369f22c8dd32d4d053a1bf92b8a3c858`

> Attendance in this release  Employees could not submit attendance correction requests. They sent the original times, proposed times, and reason to their manager. Managers directly adjusted unlocked records within 30 calendar days; older or locked periods required HR Payroll. Attendance Correction Guide v1 contains that historical procedure.

## T03 · answered

У PeopleFlow v2.0 як скасувати погоджену відпустку до першої запланованої зміни та чи потрібен квиток HR Support?

Access: all_employees.

- **action**: Open the approved request, choose Cancel leave, review and confirm before the first scheduled shift starts. Qualifications: Current self-service; not the v1.8 support-mediated cancellation. Sources: E1, E2, E3. Check: semantic.
- **ticket**: No HR Support ticket is required for this unstarted cancellation. Qualifications: Cancellation is immediate and restores the balance; started leave instead needs HR review. Sources: E1. Check: semantic.

Label note: Current-version trap against Leave Request Guide v1 and release notes v1.8.

**E1: Leave Request Guide v2 / Leave Request Guide v2 > Cancel before leave starts (v2.0)** · `F06-cbf4ce8fcbaf8bc32174326af396565bb05adbe6bd9494fd194d00dc0f29136e`

> Cancel before leave starts  Open the pending or approved request and choose Cancel leave. Review the complete cancellation, confirm it, and check the new Cancelled status. PeopleFlow immediately restores the reservation or deduction and notifies the manager. No new manager approval or HR Support ticket is required. Partial cancellation is not available: cancel the entire unstarted request and submit a replacement for the dates still needed. The replacement needs approval and may encounter changed availability.

**E2: Annual Leave Request Guide / Annual Leave Request Guide > Status and cancellation (v2.0)** · `M03-81c54e0c088b4a97b8d5c8f997843e854233867e6e695ed58897b8e45e415fe8`

> Status and cancellation  Draft has no approval effect. Pending waits for the assigned manager; Approved authorizes the absence; Rejected records a reason. From v2.0, employees may cancel their own pending or approved annual leave before its first scheduled shift begins. Open the request, choose Cancel leave, review the released days, and confirm. Cancellation is immediate, restores the reservation or deduction, and notifies the manager. A started absence requires HR review and cannot be cancelled through self-service.

**E3: Employee FAQ / Employee FAQ > Can I cancel approved leave? (v2.0)** · `F01-1832224ac45338b96adac4735fb570b0aba389a8f2a0ac8cecad43f08f9f26d5`

> Can I cancel approved leave?  Yes. In v2.0, open the request and choose Cancel leave before its first scheduled shift starts. This releases the balance immediately and notifies the manager. After leave starts, ask HR for review.

## N03 · unavailable

У PeopleFlow v3.0 який строк самостійного виправлення обліку часу?

Access: all_employees.

- **Must identify as unavailable:** Attendance self-service correction rule applicable to v3.0.

Label note: Only v1.8 and v2.0 are documented. Do not project the v2.0 rule onto an undocumented named version.

No positive evidence is labeled. Confirm absence across the canonical corpus,
not only among retrieved excerpts.
