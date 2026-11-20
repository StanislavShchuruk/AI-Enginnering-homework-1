# PeopleFlow RAG baseline — provisional

Label status: draft. Semantic review is required.

Cases attempted: 20; valid structures: 19; outcomes: {'valid_answer': 19, 'response_validation_error': 1}.

Status matches: 16/19.

Citation membership: 19/19.

Lexical key-fact matches: 12/17; semantic-only facts unscored: 13.

Expected-source matches on lexically matched facts: 11/12.

These are separate signals, not answer accuracy. Lexical misses can be paraphrases;
lexical matches can omit qualifications or express negation. All cases need semantic review.

| Case | Outcome | Status match | Citation IDs | Key facts (lexical) | Observed failures |
| --- | --- | --- | --- | --- | --- |
| R01 | valid_answer | True | pass | 1/1 | None detected automatically; review required |
| R02 | valid_answer | True | pass | 1/1 | None detected automatically; review required |
| R03 | valid_answer | True | pass | 0/0 | None detected automatically; review required |
| R04 | valid_answer | True | pass | 1/1 | None detected automatically; review required |
| R05 | valid_answer | True | pass | 1/3 | window:key_fact_not_matched; unlocked:key_fact_not_matched |
| R06 | valid_answer | False | pass | 0/0 | status_mismatch |
| R07 | valid_answer | True | pass | 0/0 | None detected automatically; review required |
| R08 | valid_answer | True | pass | 3/3 | None detected automatically; review required |
| R09 | response_validation_error | None | not_scored | 0/0 | response_schema_or_citation_validation_failed; response_schema_invalid |
| R10 | valid_answer | True | pass | 0/0 | None detected automatically; review required |
| R11 | valid_answer | True | pass | 1/1 | None detected automatically; review required |
| R12 | valid_answer | True | pass | 3/3 | None detected automatically; review required |
| N01 | valid_answer | True | pass | 0/0 | None detected automatically; review required |
| N02 | valid_answer | True | pass | 0/0 | None detected automatically; review required |
| P01 | valid_answer | True | pass | 0/1 | window:key_fact_not_matched |
| P02 | valid_answer | False | pass | 1/1 | status_mismatch; duration:expected_source_not_cited_for_matched_fact |
| T01 | valid_answer | True | pass | 0/1 | days:key_fact_not_matched |
| T02 | valid_answer | True | pass | 0/1 | window:key_fact_not_matched |
| T03 | valid_answer | True | pass | 0/0 | None detected automatically; review required |
| N03 | valid_answer | False | pass | 0/0 | status_mismatch |
