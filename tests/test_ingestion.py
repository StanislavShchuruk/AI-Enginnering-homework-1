"""Offline sanitizer, pre-redaction hashing and ingestion boundary regressions."""

import hashlib
import json
import re
from itertools import permutations
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_project.cli import main
from ai_project.deduplication import canonical_content, content_hash, deduplicate, source_hash
from ai_project.extraction.models import ContentBlock, ExtractedDocument
from ai_project.ingestion import load_config, process_corpus
from ai_project.sanitization import SanitizationConfig, sanitize_document

ROOT = Path(__file__).resolve().parents[1]
META = {
    "access_group": "hr_confidential",
    "status": "active",
    "version": "2.0",
    "effective_date": "2026-09-01",
    "supersedes": None,
    "superseded_by": None,
}


def document(text: str, identifier: str = "T01") -> ExtractedDocument:
    return ExtractedDocument(
        document_id=identifier,
        source_path=f"data/documents/{identifier}.md",
        title="HR policy",
        format="markdown",
        metadata=dict(META),
        blocks=[
            ContentBlock(
                type="heading", text="HR policy", heading_level=1, section_path=["HR policy"]
            ),
            ContentBlock(type="paragraph", text=text, section_path=["HR policy"]),
        ],
    )


def test_identifiers_names_and_addresses() -> None:
    raw = document(
        "Alice Morgan; alice.morgan@example.com; +1 202-555-0154; EMP-8472; "
        "31 Oak Street, Oakville, OR 97000. Employee: Alice Morgan."
    )
    before = raw.model_dump_json()
    sanitized = sanitize_document(raw)
    text = sanitized.blocks[1].text
    assert text == ("[PERSON]; [EMAIL]; [PHONE]; [EMPLOYEE_ID]; [ADDRESS]. Employee: [PERSON].")
    assert sanitized.redaction_counts == {
        "PERSON": 2,
        "EMAIL": 1,
        "PHONE": 1,
        "EMPLOYEE_ID": 1,
        "ADDRESS": 1,
    }
    assert raw.model_dump_json() == before
    assert sanitized.metadata == raw.metadata and sanitized.metadata is not raw.metadata
    assert sanitized.blocks[0] == raw.blocks[0]


def test_configurable_detection_and_document_wide_name_replacement() -> None:
    raw = document(
        "Staff member = maria del rio; residence = Apt 9, Example Building. "
        "maria del rio approved the request."
    )
    config = SanitizationConfig(
        person_patterns=[r"Staff member = (?P<pii>[^;]+)"],
        address_patterns=[],
        address_values=["Apt 9, Example Building"],
    )
    text = sanitize_document(raw, config).blocks[1].text
    assert text == "Staff member = [PERSON]; residence = [ADDRESS]. [PERSON] approved the request."


def test_subsequent_full_first_and_last_name_references() -> None:
    raw = document(
        "Employee: Alice Morgan. Alice should review the schedule. "
        "Alice Morgan must sign. Morgan confirmed the details. Alice's signature is due."
    )
    raw.blocks.append(
        ContentBlock(
            type="paragraph", text="Ms. Morgan signed the agreement.", section_path=["HR policy"]
        )
    )
    before = raw.model_dump_json()
    sanitized = sanitize_document(raw)
    assert sanitized.blocks[1].text == (
        "Employee: [PERSON]. [PERSON] should review the schedule. [PERSON] must sign. "
        "[PERSON] confirmed the details. [PERSON]'s signature is due."
    )
    assert sanitized.blocks[2].text == "Ms. [PERSON] signed the agreement."
    assert sanitized.redaction_counts == {"PERSON": 6}
    assert raw.model_dump_json() == before
    for old, new in zip(raw.blocks, sanitized.blocks, strict=True):
        assert old.section_path == new.section_path and old.location == new.location
    assert raw.metadata == sanitized.metadata


def test_short_references_require_previously_identified_full_name() -> None:
    raw = document(
        "Alice should review the schedule. Employee: Alice Morgan. Alice should review it again."
    )
    assert sanitize_document(raw).blocks[1].text == (
        "Alice should review the schedule. Employee: [PERSON]. [PERSON] should review it again."
    )


def test_shared_name_parts_are_reported_without_raw_values() -> None:
    raw = document(
        "Employee: Alice Morgan. Employee: Alice Carter. Alice should sign. "
        "Morgan should review the schedule."
    )
    sanitized = sanitize_document(raw)
    assert sanitized.blocks[1].text == (
        "Employee: [PERSON]. Employee: [PERSON]. Alice should sign. "
        "[PERSON] should review the schedule."
    )
    warning = next(w for w in sanitized.warnings if "shared_name_part" in w)
    assert "1 occurrences" in warning and "Alice" not in warning


def test_common_words_and_unsupported_alias_context_are_preserved() -> None:
    raw = document(
        "Employee: Will May. May is the annual review month. "
        "Will should review the schedule. Employee: Alice Morgan. "
        "Morgan Policy remains in effect; will grant leave by 1 May."
    )
    sanitized = sanitize_document(raw)
    assert sanitized.blocks[1].text == (
        "Employee: [PERSON]. May is the annual review month. "
        "Will should review the schedule. Employee: [PERSON]. "
        "Morgan Policy remains in effect; will grant leave by 1 May."
    )
    assert any("common_word_or_short_name" in w for w in sanitized.warnings)
    assert any("insufficient_person_context" in w for w in sanitized.warnings)


def test_short_names_do_not_leak_across_documents_or_change_headings() -> None:
    sanitize_document(document("Employee: Alice Morgan. Alice should review."))
    unrelated = document("Alice should review the schedule.")
    assert sanitize_document(unrelated).blocks == unrelated.blocks
    raw = document("Employee: Alice Morgan. Alice should review the schedule.")
    raw.blocks.append(ContentBlock(type="heading", text="Morgan policy", heading_level=2))
    assert sanitize_document(raw).blocks[-1] == raw.blocks[-1]


@pytest.mark.parametrize(
    "text",
    [
        "Email: a.person@example.com; telephone (202) 555-0160",
        "Email: a.person@example.com; telephone +44 20 1234 5678",
        "Email: a.person@example.com; telephone +380501234567",
        "Email: a.person@example.com; telephone: 2025550160",
    ],
)
def test_phone_forms(text: str) -> None:
    output = sanitize_document(document(text))
    assert output.redaction_counts == {"EMAIL": 1, "PHONE": 1}


def test_bank_identifiers_and_money() -> None:
    text = (
        "account: ****4826; routing: *****6214; account number: 123456789012; "
        "routing number: 987654321; USD 4,200.00 less USD 840.00 equals USD 3,360.00. "
        "PAY-EXPORT-017; overtime 1.5; 40 hours/week; 25 days per calendar year."
    )
    result = sanitize_document(document(text))
    assert result.redaction_counts == {"BANK_ACCOUNT": 2, "BANK_ROUTING": 2}
    for fact in [
        "USD 4,200.00",
        "USD 840.00",
        "USD 3,360.00",
        "PAY-EXPORT-017",
        "1.5",
        "40 hours/week",
        "25 days per calendar year",
    ]:
        assert fact in result.blocks[1].text


def test_individual_medical_case_and_general_policy() -> None:
    raw = document(
        "Alice Morgan, EMP-8472, absent 2026-09-21 through 2026-09-23 for influenza "
        "symptoms. Contract A: 10 paid sick days; charged: 3 days; remaining: 7 days. "
        "Evidence status: self-certified."
    )
    result = sanitize_document(raw)
    assert "influenza" not in result.blocks[1].text
    assert "2026-09-21" not in result.blocks[1].text
    assert "self-certified" not in result.blocks[1].text
    assert "10 paid sick days; charged: 3 days; remaining: 7 days" in result.blocks[1].text
    policy = document(
        "Employees absent for influenza symptoms follow policy. "
        "The first three scheduled days may be self-certified; evidence is "
        "required from the fourth. Report within two business days."
    )
    assert sanitize_document(policy).blocks == policy.blocks
    mixed = sanitize_document(
        document("Alice Morgan, EMP-8472, reported migraine symptoms, gross USD 4,200.00.")
    )
    assert "migraine" not in mixed.blocks[1].text
    assert "gross USD 4,200.00" in mixed.blocks[1].text
    business = document(
        "Annual Leave; 25 days per calendar year. Payroll Cutoff; 20 days. "
        "Retain records under Employee Data Privacy Policy; an investigation "
        "hold pauses routine deletion."
    )
    assert sanitize_document(business).blocks == business.blocks
    clinical_email = sanitize_document(
        document("patient@example.com reported migraine on 2026-09-14.")
    )
    assert "migraine" not in clinical_email.blocks[1].text
    assert clinical_email.redaction_counts == {"EMAIL": 1, "MEDICAL_INFO": 1}


def test_table_list_structure_and_nonsemantic_furniture() -> None:
    raw = document("Body")
    raw.blocks.extend(
        [
            ContentBlock(
                type="table",
                rows=[
                    ["Employee", "Alice Morgan"],
                    ["ID", "EMP-8472"],
                    ["Diagnosis", "migraine"],
                    ["Salary", "USD 4,200.00"],
                ],
                text=(
                    "Employee\tAlice Morgan\nID\tEMP-8472\nDiagnosis\tmigraine\n"
                    "Salary\tUSD 4,200.00"
                ),
                section_path=["HR policy"],
            ),
            ContentBlock(
                type="list_item",
                text="Contact alice.morgan@example.com",
                marker="3)",
                ordered=True,
                list_level=1,
                section_path=["HR policy"],
                location={"page": 2, "bbox": [20, 30, 80, 40]},
            ),
            ContentBlock(type="footer", text="alice.morgan@example.com", location={"page": 2}),
        ]
    )
    result = sanitize_document(raw)
    assert result.blocks[2].rows == [
        ["Employee", "[PERSON]"],
        ["ID", "[EMPLOYEE_ID]"],
        ["Diagnosis", "[MEDICAL_INFO]"],
        ["Salary", "USD 4,200.00"],
    ]
    assert result.blocks[2].text == "\n".join("\t".join(row) for row in result.blocks[2].rows)
    assert result.redaction_counts["PERSON"] == 1  # Table text isn't counted a second time.
    for old, new in zip(raw.blocks, result.blocks, strict=True):
        assert old.type == new.type and old.section_path == new.section_path
        assert old.location == new.location and old.marker == new.marker
        assert old.ordered == new.ordered and old.list_level == new.list_level
    assert result.blocks[-1].text == "[EMAIL]" and not result.blocks[-1].is_semantic
    assert result.blocks[-1] not in result.semantic_blocks
    assert b"alice.morgan" not in canonical_content(result)


@pytest.mark.parametrize("field", ["title", "metadata", "heading", "section", "marker", "location"])
def test_protected_fields_with_pii_fail_without_leaking(field: str) -> None:
    raw = document("Body")
    pii = "private.person@example.com"
    if field == "metadata":
        raw.metadata["note"] = pii
    elif field == "heading":
        raw.blocks[0].text = pii
    elif field == "section":
        raw.blocks[1].section_path = [pii]
    elif field == "marker":
        raw.blocks[1].marker = pii
    elif field == "location":
        raw.blocks[1].location.part = pii
    else:
        raw.title = pii
    with pytest.raises(ValueError) as error:
        sanitize_document(raw)
    assert pii not in str(error.value)


def test_config_validation_and_reported_limitations(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"person_values": ["Unlabeled Person"]}', encoding="utf-8")
    config = load_config(path)
    result = sanitize_document(document("Unlabeled Person"), config)
    assert result.blocks[1].text == "[PERSON]"
    assert any("best effort" in warning for warning in result.warnings)
    with pytest.raises(ValueError):
        SanitizationConfig(person_patterns=["["])
    with pytest.raises(ValueError):
        SanitizationConfig(person_patterns=[".*"])
    with pytest.raises(ValueError):
        SanitizationConfig(person_values=[""])
    with pytest.raises(ValueError):
        load_config(tmp_path / ".env")


def test_hash_canonicalization_and_semantic_only() -> None:
    first = document("25 days\n  per calendar year")
    other = document("25 days per\tcalendar year", "T02")
    other.blocks.append(ContentBlock(type="header", text="An entirely different running header"))
    other.blocks[1].location.page = 9
    assert content_hash(first) == content_hash(other)
    assert source_hash(b"same bytes") == hashlib.sha256(b"same bytes").hexdigest()
    assert source_hash(b"same bytes") != source_hash(b"same  bytes")
    other.blocks[1].text = "15 days per calendar year"
    assert content_hash(first) != content_hash(other)
    table = first.model_copy(deep=True)
    table.blocks.append(ContentBlock(type="table", text="A\tB", rows=[["A", "B"]]))
    table2 = table.model_copy(deep=True)
    table2.blocks[-1].text = "different rendered whitespace"
    table2.blocks[-1].rows = [[" A ", " B\n"]]
    assert content_hash(table) == content_hash(table2)
    table2.blocks[-1].rows = [["A B"]]
    assert content_hash(table) != content_hash(table2)


def record(doc: ExtractedDocument, data: bytes = b"source") -> dict:
    return {
        "document_id": doc.document_id,
        "source_hash": source_hash(data),
        "content_hash": content_hash(doc),
        "metadata": doc.metadata,
    }


def test_deduplication_deterministic_and_access_and_history_safe() -> None:
    first, duplicate = document("25 days", "A01"), document("25 days", "A02")
    historical = document("25 days", "H01")
    historical.metadata.update(status="superseded", version="1.8")
    public = document("25 days", "P01")
    public.metadata["access_group"] = "all_employees"
    changed = document("15 days", "C01")
    records = [record(doc) for doc in [first, duplicate, historical, public, changed]]
    expected = deduplicate(records)
    second_historical = historical.model_copy(deep=True)
    second_historical.document_id = "H02"
    assert not deduplicate([record(historical), record(second_historical)])["excluded_documents"]
    assert expected["excluded_documents"] == [
        {
            "document_id": "A02",
            "kept_document_id": "A01",
            "reason": "identical_pre_redaction_content_and_policy_metadata",
        }
    ]
    assert expected["duplicate_groups"][0]["document_ids"] == ["A01", "A02", "H01", "P01"]
    for permutation in permutations(records):
        assert deduplicate(list(permutation)) == expected
    for key, value in [
        ("version", "2.1"),
        ("effective_date", "2026-10-01"),
        ("supersedes", "H01"),
        ("category", "policy"),
    ]:
        changed_metadata = duplicate.model_copy(deep=True)
        changed_metadata.metadata[key] = value
        assert not deduplicate([record(first), record(changed_metadata)])["excluded_documents"]


def test_redaction_collision_does_not_deduplicate() -> None:
    first = document("Employee: Alice Morgan; EMP-8472", "A01")
    second = document("Employee: Robert Greene; EMP-8843", "A02")
    assert content_hash(sanitize_document(first)) == content_hash(sanitize_document(second))
    assert content_hash(first) != content_hash(second)
    assert not deduplicate([record(first), record(second)])["duplicate_groups"]


def project_fixture(root: Path) -> list[dict]:
    (root / "data/documents").mkdir(parents=True)
    entries = []
    for identifier in ["T02", "T01"]:
        entry = {
            "document_id": identifier,
            "path": f"data/documents/{identifier}.md",
            "title": "HR policy",
            "format": "markdown",
            **META,
        }
        entries.append(entry)
        (root / entry["path"]).write_text(
            "# HR policy\n\nEmployee: Alice Morgan; EMP-8472; "
            "alice.morgan@example.com. 25 leave days.",
            encoding="utf-8",
        )
    (root / "data/manifest.json").write_text(json.dumps(entries), encoding="utf-8")
    return entries


def test_pipeline_and_cli_deterministic_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = tmp_path / "project"
    entries = project_fixture(root)
    output = tmp_path / "first"
    assert main(["ingest-corpus", "--project-root", str(root), "--output", str(output)]) == 0
    assert "alice.morgan" not in capsys.readouterr().out
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["sanitized_documents"] == 2 and report["included_documents"] == 1
    assert report["excluded_documents"][0]["document_id"] == "T02"
    assert (output / "documents/T01.json").exists()
    assert (output / "duplicates/T02.json").exists()
    entries.reverse()
    (root / "data/manifest.json").write_text(json.dumps(entries), encoding="utf-8")
    process_corpus(root, root / "data/manifest.json", tmp_path / "second")
    for path in output.rglob("*.json"):
        assert path.read_bytes() == (tmp_path / "second" / path.relative_to(output)).read_bytes()
        assert b"alice.morgan" not in path.read_bytes() and b"Alice Morgan" not in path.read_bytes()
    with pytest.raises(FileExistsError):
        process_corpus(root, root / "data/manifest.json", output)
    with pytest.raises(ValueError):
        process_corpus(root, root / "data/manifest.json", root / "data/documents/generated")


def test_processing_errors_do_not_expose_pii(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    root = tmp_path / "project"
    project_fixture(root)

    def bad_parser(*args: object) -> None:
        print("alice.morgan@example.com")
        raise ValueError("Employee Alice Morgan alice.morgan@example.com")

    with patch("ai_project.ingestion.extract_document", side_effect=bad_parser):
        assert (
            main(
                ["ingest-corpus", "--project-root", str(root), "--output", str(tmp_path / "failed")]
            )
            == 1
        )
    report = (tmp_path / "failed/report.json").read_text(encoding="utf-8")
    assert "Alice Morgan" not in report and "alice.morgan" not in report
    assert "alice.morgan" not in capsys.readouterr().out
    assert json.loads(report)["withheld_documents"] == 2
    assert not list((tmp_path / "failed/documents").iterdir())


def test_real_corpus_sanitization_and_input_preservation(tmp_path: Path) -> None:
    extracted = ROOT / "data/extracted"
    if not extracted.is_dir():
        pytest.skip("Existing extracted corpus is unavailable")
    manifest = json.loads((ROOT / "data/manifest.json").read_text(encoding="utf-8"))
    inputs = [ROOT / entry["path"] for entry in manifest]
    inputs.extend(extracted / (entry["document_id"] + ".json") for entry in manifest)
    before = {path: source_hash(path.read_bytes()) for path in inputs}
    output = tmp_path / "sanitized"
    report = process_corpus(ROOT, ROOT / "data/manifest.json", output, extracted=extracted)
    assert report["sanitized_documents"] == report["included_documents"] == 32
    assert not report["errors"] and not report["duplicate_groups"]
    assert report["redaction_counts"] == {
        "PERSON": 17,
        "EMAIL": 4,
        "PHONE": 3,
        "EMPLOYEE_ID": 6,
        "ADDRESS": 3,
        "BANK_ACCOUNT": 3,
        "BANK_ROUTING": 2,
        "MEDICAL_INFO": 4,
    }
    # Fixed authored examples are QA fixtures only; no such list exists in production.
    forbidden = [
        "Laura Bennett",
        "Daniel Mercer",
        "Rachel Collins",
        "Adrian Foster",
        "Hannah Reed",
        "Oliver Hayes",
        "Sophia Grant",
        "Natalie Brooks",
        "Emily Carter",
        "Silverfern Rise",
        "Ashgrove Terrace",
        "Willowmere Way",
        "migraine",
        "influenza",
        "2026-09-14",
        "2026-09-16",
        "2026-09-21",
        "2026-09-23",
    ]
    for entry in manifest:
        raw = ExtractedDocument.model_validate_json(
            (extracted / (entry["document_id"] + ".json")).read_text(encoding="utf-8")
        )
        payload = json.loads(
            (output / "documents" / (entry["document_id"] + ".json")).read_text(encoding="utf-8")
        )
        sanitized = ExtractedDocument.model_validate(payload)
        assert sanitized.metadata == raw.metadata
        assert payload["source_hash"] == before[ROOT / entry["path"]]
        assert payload["content_hash"] == content_hash(raw)
        assert len(raw.blocks) == len(sanitized.blocks)
        for old, new in zip(raw.blocks, sanitized.blocks, strict=True):
            assert old.type == new.type and old.section_path == new.section_path
            assert old.location == new.location and old.marker == new.marker
            assert old.ordered == new.ordered and old.list_level == new.list_level
            assert re.findall(r"USD [\d,.]+", old.text) == re.findall(r"USD [\d,.]+", new.text)
            if old.type == "heading" or not entry["contains_synthetic_pii"]:
                assert old.text == new.text
        semantic = canonical_content(sanitized).decode("utf-8")
        assert not any(value in semantic for value in forbidden)
        person_names = forbidden[:9]
        assert not any(
            re.search(r"(?<!\w)" + re.escape(part) + r"(?!\w)", semantic)
            for name in person_names
            for part in name.split()
        )
        assert not any(
            "Ambiguous short-name references retained:" in w for w in payload["warnings"]
        )
        assert not re.search(
            r"[\w.+-]+@[\w.-]+|\bEMP-\d+\b|\*{3,}\d+|\+1 \d{3}-555-\d{4}", semantic
        )
    assert {path: source_hash(path.read_bytes()) for path in inputs} == before


def test_independent_sanitize_cli_and_metadata_mismatch(tmp_path: Path) -> None:
    from ai_project.extraction.corpus import extract_corpus

    root = tmp_path / "project"
    project_fixture(root)
    extracted = tmp_path / "extracted"
    extract_corpus(root, root / "data/manifest.json", extracted)
    assert (
        main(
            [
                "sanitize-corpus",
                "--project-root",
                str(root),
                "--input",
                str(extracted),
                "--output",
                str(tmp_path / "sanitized"),
            ]
        )
        == 0
    )
    path = extracted / "T01.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["metadata"]["access_group"] = "all_employees"
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = process_corpus(
        root, root / "data/manifest.json", tmp_path / "mismatch", extracted=extracted
    )
    assert report["withheld_documents"] == 1
    assert report["errors"][0]["document_id"] == "T01"
    assert not (tmp_path / "mismatch/documents/T01.json").exists()
    with pytest.raises(ValueError):
        process_corpus(
            root, root / "data/manifest.json", extracted / "sanitized", extracted=extracted
        )
    # Reprocessing sanitized files must not turn post-redaction hashes into dedup keys.
    report = process_corpus(
        root,
        root / "data/manifest.json",
        tmp_path / "already-sanitized",
        extracted=tmp_path / "sanitized/documents",
    )
    assert report["sanitized_documents"] == 0
    assert report["withheld_documents"] == 2
