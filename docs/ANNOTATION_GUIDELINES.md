# HR ticket annotation guidelines

## Status and review

The output fields, enums, required nullable fields, and action limit are the agreed
schema contract. The decision rules below document a working annotation policy
consistent with the visible golden labels. Tie-break rules and ambiguity decisions
must be confirmed during manual review; they do not automatically relabel any case.
Never infer missing facts merely to fill a field. Dataset and golden-label changes
require human review.

## File structure and IDs

data/tickets.json must be a JSON array containing exactly 30 ticket objects.
data/golden_set.json must be a JSON array containing exactly 10 case objects,
each with an id and an expected HRSupportTicket object. IDs must be unique integers
within each file; booleans are not IDs. Every golden ID must identify an input ticket.
The golden set is a subset, so not all input IDs need golden labels.
Repeated JSON object keys are invalid for this project: they can silently discard labels.

## Category

Select one primary category based on the user's affected workflow and main request:

| Value | Rule |
| --- | --- |
| authentication | Sign-in, passwords, account lockout, or authentication failures. |
| absence | Leave, holiday, sickness, absence balances, or absence requests. |
| attendance | Clock-in/out, worked hours, time records, or time corrections. |
| shifts | Shift schedules, assignments, swaps, or viewing the work rota. |
| payroll | Salary, payslips, deductions, allowances, or missing/incorrect pay. |
| employee_profile | Personal details, employee records, or profile changes. |
| technical | General application failures without a more specific HR workflow. |
| other | Requests outside these categories or too unclear to classify. |

A frozen absence request page remains absence; a shift schedule that fails to load
remains shifts. A generic calendar failure can be technical. For multiple issues,
choose the main requested resolution. Explicit payroll impact takes precedence over
attendance when payroll is the main problem (for example missing hours threatening
pay for multiple employees). If the primary issue remains ambiguous, flag it for
manual review rather than inventing an additional category.

## Priority

- low: Informational/how-to requests or minor issues with no stated disruption.
- medium: A concrete issue disrupting an employee workflow without evidence of
  critical impact or a time-critical deadline.
- high: Explicit major impact, such as multiple employees unable to work or
  a payroll deadline at risk. Do not infer high priority from frustration alone.
- unknown: Insufficient information to judge impact or urgency.

Use stated evidence; payroll and technical categories are not automatically high.

## Language

Use en for English, uk for Ukrainian, and ru for Russian. Label the language of the
original user message, not quoted error text, product names, or translated summaries.
For mixed messages, use the predominant language of the user's meaningful prose.
If there is no clear dominant language, require manual review. There is no unknown
language enum; do not silently map an unsupported language to one of these values.
Prefer writing summary and actions in the user's language; existing translations
must be reviewed manually rather than rewritten automatically.

## Application

Extract the explicitly named application, or use null when absent or ambiguous.
Do not infer a product from its workflow or error code. Trim surrounding whitespace
and retain the stated name. Do not expand ESS or normalize product aliases/casing
without a separately reviewed mapping. Existing HR Portal/HR portal variants are
not automatically changed by this policy.

## requires_support

true means resolving the reported issue currently requires intervention by a human
manager, HR/payroll staff, administrator, or technical support. This includes incorrect
records, unresolved access failures, and application defects requiring investigation.
false means a general how-to or self-service request can plausibly be answered
without intervention. It does not mean that suggested_actions must be empty.
A conditional escalation in a how-to answer does not alone make this field true.
When evidence is ambiguous, flag for manual review; the schema has no null value.

## suggested_actions

Provide zero to three concise, distinct, relevant actions grounded in the ticket.
Use an empty list if no justified action can be suggested. Prefer safe self-service
steps when appropriate, followed by the relevant human escalation if needed.
Do not claim an action has been performed, invent product navigation, request
passwords/API keys, or recommend unverified changes to payroll or employee records.
Actions are recommendations, not automated execution.

## Other output fields

summary is a concise factual description without invented causes or outcomes.
details.error_code and details.error_message contain explicitly reported error
information; use null for each unknown value. Preserve the reported error wording.
All schema fields must be present, including application and both details fields
when null. Additional fields are not allowed.

## Automated validation

Run python -m pytest from the project root after installing the dev dependencies.
Tests check file parsing, counts, unique integer IDs, golden-to-input ID references,
and every expected output against HRSupportTicket. They do not establish semantic
label correctness, language distribution, or agreement with these decision rules;
those still need manual review. Validation never modifies either JSON file.
