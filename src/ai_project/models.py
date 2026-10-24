"""Validated structured output for HR support ticket extraction."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr


class TicketCategory(str, Enum):
    AUTHENTICATION = "authentication"
    ABSENCE = "absence"
    ATTENDANCE = "attendance"
    SHIFTS = "shifts"
    PAYROLL = "payroll"
    EMPLOYEE_PROFILE = "employee_profile"
    TECHNICAL = "technical"
    OTHER = "other"


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class TicketLanguage(str, Enum):
    EN = "en"
    UK = "uk"
    RU = "ru"


class TicketDetails(BaseModel):
    """Error information; unknown values must explicitly be null."""

    model_config = ConfigDict(extra="forbid")

    error_code: StrictStr | None
    error_message: StrictStr | None


class HRSupportTicket(BaseModel):
    """Every field is required, even when its value may be null."""

    model_config = ConfigDict(extra="forbid")

    summary: StrictStr
    category: TicketCategory
    priority: TicketPriority
    application: StrictStr | None
    language: TicketLanguage
    requires_support: StrictBool
    details: TicketDetails
    suggested_actions: list[StrictStr] = Field(max_length=3)
