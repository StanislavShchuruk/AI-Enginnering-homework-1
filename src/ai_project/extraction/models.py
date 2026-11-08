"""Inspection-oriented extraction schema; no retrieval or text rewriting."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DocumentFormat = Literal["pdf", "docx", "html", "markdown"]


class SourceLocation(BaseModel):
    page: int | None = Field(default=None, ge=1)
    bbox: tuple[float, float, float, float] | None = None
    element: int | None = Field(default=None, ge=0)
    line: int | None = Field(default=None, ge=1)
    part: str | None = None


class ContentBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["heading", "paragraph", "list_item", "table", "page_break", "header", "footer"]
    text: str
    section_path: list[str] = Field(default_factory=list)
    heading_level: int | None = Field(default=None, ge=1)
    ordered: bool | None = None
    list_level: int | None = Field(default=None, ge=0)
    marker: str | None = None
    rows: list[list[str]] | None = None
    location: SourceLocation = Field(default_factory=SourceLocation)
    is_semantic: bool = True

    @model_validator(mode="after")
    def validate_structure(self) -> "ContentBlock":
        # Derive this on load as well as extraction; consumers cannot accidentally
        # opt furniture into semantic content by passing an inconsistent flag.
        self.is_semantic = self.type not in {"header", "footer", "page_break"}
        if not self.is_semantic:
            self.section_path = []
        if self.type == "heading" and self.heading_level is None:
            raise ValueError("Headings require a level")
        if self.type == "table" and not self.rows:
            raise ValueError("Tables require rows")
        if self.type == "list_item" and self.ordered is None:
            raise ValueError("List items require an ordered flag")
        if self.type != "page_break" and not self.text.strip():
            raise ValueError("Content blocks must have text")
        return self


class ExtractedDocument(BaseModel):
    schema_version: str = "1.1"
    document_id: str
    source_path: str
    title: str
    format: DocumentFormat
    metadata: dict[str, Any]
    blocks: list[ContentBlock]
    warnings: list[str] = Field(default_factory=list)

    @property
    def semantic_blocks(self) -> list[ContentBlock]:
        """Ordered body content for future consumers; furniture remains in blocks."""
        return [block for block in self.blocks if block.is_semantic]
