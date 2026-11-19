"""Deterministic, local PII redaction with configurable contextual detection.

This is a best-effort detector, not an anonymization or access-control guarantee.
Never log matched values. Counts describe replacements, not distinct people.
"""

import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_project.extraction.models import ExtractedDocument

Category = Literal[
    "PERSON",
    "EMAIL",
    "PHONE",
    "EMPLOYEE_ID",
    "ADDRESS",
    "BANK_ACCOUNT",
    "BANK_ROUTING",
    "MEDICAL_INFO",
]
NAME = r"[A-ZÀ-ÖØ-Þ][\w'’-]+(?:[ \t]+[A-ZÀ-ÖØ-Þ][\w'’-]+){1,3}"
# Ordinary vocabulary/months can also be personal names. These are ambiguity
# guards, not a list of corpus identities; callers can extend this configuration.
COMMON_NAME_WORDS = """
may will bill mark grant rose grace hope april june march summer autumn day
brown green white black long short young king read cook pay leave best west north south
""".split()
PERSON_PATTERNS = [
    rf"(?m)^(?P<pii>{NAME})(?=[,;]\s*(?:employee\s+)?(?:EMP-|[\w.+-]+@|\+\d))",
    rf"\b(?:Employee(?: name)?|Patient|Name):[ \t]*(?P<pii>{NAME})\b",
    rf"\b(?:Employee|employee|Patient|patient)[ \t]+(?P<pii>{NAME})"
    rf"(?=[,;]?[ \t]+(?:reported|was|has|is|will)\b)",
    rf"\bSigned by[ \t]+(?P<pii>{NAME})(?=:)",
    rf"\band[ \t]+(?P<pii>{NAME})[ \t]+\(the Employee\)",
    rf"\boffers[ \t]+(?P<pii>{NAME})[ \t]+employment\b",
    rf"\band[ \t]+(?P<pii>{NAME})[ \t]+agree\b",
    rf"(?m)^Employee\t(?P<pii>{NAME})(?=\t|\n|$)",
]
ADDRESS_PATTERNS = [
    r"\b\d{1,6}[ \t]+[A-Za-z0-9 .'’-]{1,70}?[ \t]+"
    r"(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Dr|Way|Rise|Terrace|Court|Ct|Boulevard|Blvd)"
    r"\b(?:,[ \t]*[A-Za-z .'’-]+,[ \t]*[A-Z]{2}[ \t]+\d{5}(?:-\d{4})?)?",
]
LIMITATIONS = [
    "Deterministic redaction is best effort; unrecognized or unlabeled PII may remain.",
    "Name rules depend on English context and capitalization; configure patterns or values "
    "for other languages, naming conventions, and unlabeled names.",
    "Default address rules target numbered North American street addresses; configure "
    "patterns or values for other address formats.",
    "Phone, employee-ID, bank and medical rules cover common explicit forms, not every "
    "identifier or clinical narrative. Indirect identifiers and reidentification are not assessed.",
    "Sanitization does not change access permissions; authorization is required downstream.",
    "Short-name references require a previously identified full name, unique ownership, "
    "and person-specific context; ambiguous references are retained and reported without values.",
]


class SanitizationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person_patterns: list[str] = Field(default_factory=lambda: list(PERSON_PATTERNS))
    address_patterns: list[str] = Field(default_factory=lambda: list(ADDRESS_PATTERNS))
    person_values: list[str] = Field(default_factory=list)
    address_values: list[str] = Field(default_factory=list)
    ambiguous_name_parts: list[str] = Field(default_factory=lambda: list(COMMON_NAME_WORDS))
    medical_terms: list[str] = Field(
        default_factory=lambda: [
            "migraine",
            "influenza",
            "diagnosis",
            "diagnosed",
            "symptoms",
            "clinician",
            "medical certificate",
            "medical note",
            "treatment",
            "patient",
        ]
    )

    @field_validator("person_patterns", "address_patterns")
    @classmethod
    def validate_patterns(cls, values: list[str]) -> list[str]:
        for value in values:
            try:
                pattern = re.compile(value)
            except re.error:
                raise ValueError("Invalid detection pattern") from None
            if pattern.search(""):
                raise ValueError("Detection patterns cannot match empty text")
        return values

    @field_validator("person_values", "address_values", "medical_terms", "ambiguous_name_parts")
    @classmethod
    def validate_values(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("Detection values must not be empty")
        return values


class SanitizedDocument(ExtractedDocument):
    sanitization_version: str = "1.1"
    redaction_counts: dict[str, int] = Field(default_factory=dict)


def discover_values(text: str, patterns: list[str], values: list[str]) -> list[str]:
    found = set(values)
    for expression in patterns:
        pattern = re.compile(expression)
        for match in pattern.finditer(text):
            value = match.group("pii") if "pii" in pattern.groupindex else match[0]
            if value:
                found.add(value)
    return sorted(found, key=lambda value: (-len(value), value))


def value_pattern(value: str) -> str:
    return r"(?<!\w)" + r"\s+".join(re.escape(part) for part in value.split()) + r"(?!\w)"


def sanitize_document(
    document: ExtractedDocument,
    config: SanitizationConfig | None = None,
) -> SanitizedDocument:
    """Return a deep sanitized copy. Protected-field conflicts fail without PII in errors.

    Headings, titles, paths, section paths and manifest metadata are protected:
    detected PII there causes rejection rather than silently changing business structure.
    Tables are sanitized cell-by-cell, then their text view is rebuilt (counted once).
    """
    config = config or SanitizationConfig()
    raw_text = "\n".join(block.text for block in document.blocks if block.type != "heading")
    addresses = discover_values(raw_text, config.address_patterns, config.address_values)
    contextual_names = [
        rf"(?m)^(?P<pii>{NAME})[,;][ \t]+(?={value_pattern(address)})" for address in addresses
    ]
    people = discover_values(
        raw_text, [*config.person_patterns, *contextual_names], config.person_values
    )
    patterns: list[tuple[Category, str]] = [
        ("EMAIL", r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w-])"),
        (
            "PHONE",
            r"(?<![\w.])(?:\+\d{1,3}[ .-]?)?(?:\(\d{2,4}\)|\d{2,4})"
            r"[ .-]\d{3,4}[ .-]\d{4}(?:[ \t]*(?:ext\.?|x)[ \t]*\d+)?(?!\w)",
        ),
        ("PHONE", r"(?<!\w)\+[1-9]\d{9,14}(?!\d)"),
        (
            "PHONE",
            r"(?i)\b(?:phone|telephone|mobile|tel)[ \t]*[:=]?[ \t]*"
            r"(?P<pii>\d{10,15})\b",
        ),
        ("EMPLOYEE_ID", r"\bEMP[- ]?\d{3,}\b"),
        (
            "EMPLOYEE_ID",
            r"(?i)\b(?:employee|staff)[ \t]+(?:id|identifier|number)"
            r"[ \t]*[:#=][ \t]*(?P<pii>[A-Z0-9][A-Z0-9-]{2,})\b",
        ),
        (
            "BANK_ROUTING",
            r"(?i)\brouting(?: number| identifier)?[ \t]*[:=][ \t]*"
            r"(?P<pii>\*{3,}\d{3,}|\d{9})\b",
        ),
        (
            "BANK_ACCOUNT",
            r"(?i)\b(?:bank account|account|payment destination)"
            r"(?: number| identifier)?[ \t]*[:=][ \t]*"
            r"(?P<pii>\*{3,}\d{3,}|[A-Z]{2}\d{2}[A-Z0-9]{11,30}|\d[\d -]{5,30}\d)\b",
        ),
        ("BANK_ACCOUNT", r"(?<!\w)\*{3,}\d{3,}\b"),
        *[("PERSON", value_pattern(value)) for value in people],
        *[("ADDRESS", value_pattern(value)) for value in addresses],
    ]
    compiled = [(category, re.compile(pattern)) for category, pattern in patterns]
    counts: Counter[str] = Counter()
    # Alias ownership is document-local and case-normalized. Shared first/last
    # names cannot be attributed safely, even when one person appears first.
    aliases: dict[str, set[str]] = {}
    owners: dict[str, set[str]] = {}
    full_patterns = {person: re.compile(value_pattern(person)) for person in people}
    for person in people:
        parts = person.split()
        if len(parts) < 2:
            continue
        for part in {parts[0], parts[-1]}:
            aliases.setdefault(part.casefold(), set()).add(part)
            owners.setdefault(part.casefold(), set()).add(" ".join(parts).casefold())
    seen_people: set[str] = set()
    ambiguous: Counter[str] = Counter()
    common_words = {value.casefold() for value in config.ambiguous_name_parts}
    person_action = re.compile(
        r"\s+(?:should|must|may|will|can|has|was|is|reported|reviewed|signed|confirmed|"
        r"approved|received|requested|submitted|agreed|needs)\b"
        r"|['’]s\s+(?:signature|schedule|profile|employment|details|request|record)\b"
    )

    def redact(text: str, medical: bool = False, count: bool = True) -> str:
        matches: list[tuple[int, int, Category]] = []
        rules = list(compiled)
        if medical:
            rules.extend(
                ("MEDICAL_INFO", re.compile(pattern, re.IGNORECASE))
                for pattern in [
                    r"\b(?:reported|diagnosed with|treated for|suffering from|absent)\s+"
                    r"(?P<pii>[^.;\n]+)",
                    r"(?P<pii>\b(?:The )?(?:clinician|doctor|physician) note[^.;\n]*)",
                    r"\b(?:Evidence status|Diagnosis|Symptoms|Medical note|Treatment):\s*"
                    r"(?P<pii>[^.;\n]+)",
                ]
            )
        for category, pattern in rules:
            for match in pattern.finditer(text):
                start, end = match.span("pii" if "pii" in pattern.groupindex else 0)
                if category == "MEDICAL_INFO":
                    # A clinical sentence may continue into payroll facts. Keep those
                    # facts verbatim instead of swallowing them into the medical span.
                    business = re.search(
                        r"\b(?:USD|salary|gross|deductions?|net|balance|charged|remaining|"
                        r"overtime|working hours|leave entitlement)\b|\$\d",
                        text[start:end],
                        re.IGNORECASE,
                    )
                    if business:
                        end = start + business.start()
                        while end > start and text[end - 1].isspace():
                            end -= 1
                if start < end:
                    matches.append((start, end, category))
        if count:
            full_matches = [
                (" ".join(person.split()).casefold(), match.start(), match.end())
                for person, pattern in full_patterns.items()
                for match in pattern.finditer(text)
            ]
            for key, spellings in sorted(aliases.items()):
                for spelling in sorted(spellings):
                    for match in re.finditer(value_pattern(spelling), text):
                        start, end = match.span()
                        if any(start >= left and end <= right for _, left, right in full_matches):
                            continue
                        if any(start >= left and end <= right for left, right, _ in matches):
                            continue
                        previous = seen_people | {
                            owner for owner, _, right in full_matches if right <= start
                        }
                        if not previous.intersection(owners[key]):
                            continue
                        reason = None
                        if len(owners[key]) != 1:
                            reason = "shared_name_part"
                        elif key in common_words or len(spelling) < 3:
                            reason = "common_word_or_short_name"
                        elif not (
                            person_action.match(text[end:])
                            or re.search(
                                r"(?:\b(?:Mr|Ms|Mrs|Dr)\.?\s+|\b(?:Employee|Patient|Name):\s*)$",
                                text[:start],
                            )
                        ):
                            reason = "insufficient_person_context"
                        if reason:
                            ambiguous[reason] += 1
                        else:
                            matches.append((start, end, "PERSON"))
            seen_people.update(owner for owner, _, _ in full_matches)
        # Prefer the widest overlapping span; routing precedes the generic mask rule.
        selected: list[tuple[int, int, Category]] = []
        priority = {"BANK_ROUTING": 0, "BANK_ACCOUNT": 1}
        for candidate in sorted(
            matches, key=lambda value: (-(value[1] - value[0]), priority.get(value[2], 2))
        ):
            start, end, _ = candidate
            if not any(start < previous[1] and end > previous[0] for previous in selected):
                selected.append(candidate)
        for start, end, category in sorted(selected, reverse=True):
            text = text[:start] + f"[{category}]" + text[end:]
            if count:
                counts[category] += 1
        return text

    # Do not copy unknown warnings (which could contain raw values) into generated output.
    protected = [document.title, document.source_path, document.document_id]
    protected.append(document.schema_version)
    protected.extend(block.marker for block in document.blocks if block.marker)
    protected.extend(block.location.part for block in document.blocks if block.location.part)
    protected.extend(block.text for block in document.blocks if block.type == "heading")
    protected.extend(value for block in document.blocks for value in block.section_path)

    def metadata_strings(value: object) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [
                s
                for key, item in value.items()
                for s in [*metadata_strings(key), *metadata_strings(item)]
            ]
        if isinstance(value, list):
            return [s for item in value for s in metadata_strings(item)]
        return []

    protected.extend(metadata_strings(document.metadata))
    if any(redact(value, count=False) != value for value in protected):
        raise ValueError("Detected PII in protected structure or metadata; document withheld")
    sanitized = SanitizedDocument.model_validate(document.model_dump()).model_copy(deep=True)
    sanitized.warnings = list(LIMITATIONS)
    if document.warnings:
        sanitized.warnings.append("Source extraction warnings exist; inspect restricted inputs.")
    for original, block in zip(document.blocks, sanitized.blocks, strict=True):
        if block.type == "heading":
            continue
        individual = bool(re.search(r"\bEMP[- ]?\d{3,}\b|[\w.+-]+@[\w.-]+", original.text)) or any(
            re.search(value_pattern(person), original.text) for person in people
        )
        clinical = individual and any(
            term.casefold() in original.text.casefold() for term in config.medical_terms
        )
        if block.rows is not None:
            medical_labels = {
                "diagnosis",
                "symptoms",
                "medical note",
                "treatment",
                "absence dates",
                "return date",
                "evidence status",
            }
            medical_columns = {
                index
                for index, cell in enumerate(block.rows[0])
                if cell.strip().casefold() in medical_labels
            }
            cleaned_rows = []
            for row_index, row in enumerate(block.rows):
                cleaned = []
                medical_row = row[0].strip().casefold() in medical_labels if row else False
                for column, cell in enumerate(row):
                    if (
                        clinical
                        and cell.strip()
                        and (
                            (medical_row and column > 0)
                            or (row_index > 0 and column in medical_columns)
                        )
                    ):
                        cleaned.append("[MEDICAL_INFO]")
                        counts["MEDICAL_INFO"] += 1
                    else:
                        cleaned.append(redact(cell, clinical))
                cleaned_rows.append(cleaned)
            block.rows = cleaned_rows
            block.text = "\n".join("\t".join(row) for row in block.rows)
        else:
            block.text = redact(block.text, clinical)
    sanitized.redaction_counts = dict(sorted(counts.items()))
    for reason, occurrences in sorted(ambiguous.items()):
        sanitized.warnings.append(
            f"Ambiguous short-name references retained: {reason} ({occurrences} occurrences)."
        )
    if document.metadata.get("contains_synthetic_pii") and not counts:
        sanitized.warnings.append(
            "Manifest flags personal examples but no supported PII was detected."
        )
    return sanitized
