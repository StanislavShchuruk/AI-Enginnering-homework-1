# PeopleFlow RAG judge and calibration

Judge: `google/gemini-3.1-flash-lite`; prompt: `rag-judge-v1`.
Prompt SHA-256: `b9c839acdd8753f0e9f32e3ce594268ccc82e040af4bd2ad09ac9af6dc223267`.

Input SHA-256:

- baseline: `2193f88e944936ca321344656a86b9adfae18968c01bea378c64d09f33933996`
- cases: `848111d4177ee4137a6ca60cc7ec72c75710e28f281d83e72d027906983d71a6`
- human_labels: `fc4355755ca61271036dec5c320389b08dbd159b0dfb4cf143bf91cbd795e7ad`

Overall: 20 cases; outcomes: {'judged': 19, 'baseline_response_validation_error': 1}.

## Human calibration (10 answers)

- Completeness: 7/10 exact agreement; 0 judge errors excluded.
- Faithfulness: 8/9 exact agreement; 0 judge errors excluded.
- Human Faithfulness n/a (excluded): N01.

## Results by subset

- calibration: {"cases": 10, "outcomes": {"judged": 10}, "completeness": {"pass": 9, "fail": 1}, "faithfulness": {"pass": 8, "n/a": 1, "fail": 1}}
- judge_only: {"cases": 9, "outcomes": {"judged": 9}, "completeness": {"pass": 9}, "faithfulness": {"pass": 8, "n/a": 1}}
- baseline_error: {"cases": 1, "outcomes": {"baseline_response_validation_error": 1}, "completeness": {}, "faithfulness": {}}

## Per-case verdicts

| Case | Subset | Outcome | Completeness | Faithfulness |
| --- | --- | --- | --- | --- |
| R01 | calibration | judged | pass | pass |
| R02 | judge_only | judged | pass | pass |
| R03 | judge_only | judged | pass | pass |
| R04 | calibration | judged | pass | pass |
| R05 | calibration | judged | pass | pass |
| R06 | calibration | judged | pass | pass |
| R07 | calibration | judged | pass | pass |
| R08 | judge_only | judged | pass | pass |
| R09 | baseline_error | baseline_response_validation_error |  |  |
| R10 | judge_only | judged | pass | pass |
| R11 | calibration | judged | pass | pass |
| R12 | judge_only | judged | pass | pass |
| N01 | calibration | judged | pass | n/a |
| N02 | judge_only | judged | pass | n/a |
| P01 | judge_only | judged | pass | pass |
| P02 | calibration | judged | pass | pass |
| T01 | calibration | judged | pass | pass |
| T02 | judge_only | judged | pass | pass |
| T03 | judge_only | judged | pass | pass |
| N03 | calibration | judged | fail | fail |

## Disagreements

### R06 / completeness

Human: **fail**. All the facts in the claims are confirmed. But the model returned partially and in missing_information it is stated that there is no way to check the balance, although she herself just listed it from S1.

Judge: **pass**. The answer correctly identifies the historical process for cancelling leave in v1.8, including contacting HR Support and the subsequent step of reopening the request to confirm the status and balance.

### R07 / completeness

Human: **fail**. The answer omits the step of submitting a replacement request for the dates the employee wants to keep.

Judge: **pass**. The answer correctly states that partial cancellation is not possible and that the entire request must be cancelled, as well as confirming that no new manager approval is required for the cancellation itself.

### P02 / completeness

Human: **fail**. The model reported that the number was not available, but returned answered instead of partial. For the 30-minute block, it only cited the historical S1 v1.8, although the context contained the current S5, which directly confirms this rule.

Judge: **pass**. The answer correctly identifies the 30-minute lockout duration and explicitly states that the requested support phone number is not available in the provided documentation.

### P02 / faithfulness

Human: **fail**. The model reported that the number was not available, but returned answered instead of partial. For the 30-minute block, it only cited the historical S1 v1.8, although the context contained the current S5, which directly confirms this rule.

Judge: **pass**. All claims are supported by the provided excerpts. The lockout duration is confirmed in S5, and the absence of the support phone number is consistent with the provided documents.


Judge verdicts are fallible semantic assessments, not ground truth. Blank human reasons are reported as absent, never inferred. Provider/schema errors are excluded from agreement, never counted as semantic failures.

Full per-claim reasons, requests, raw judge responses, and token usage are in the JSON.
