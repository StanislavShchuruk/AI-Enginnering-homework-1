"""Contract tests for structured HR ticket output."""

import json
import unittest
from typing import Any

from pydantic import ValidationError

from ai_project.models import HRSupportTicket, TicketCategory, TicketLanguage, TicketPriority


def ticket_data() -> dict[str, Any]:
    return {
        "summary": "Cannot sign in to the HR portal",
        "category": "authentication",
        "priority": "medium",
        "application": "HR Portal",
        "language": "en",
        "requires_support": True,
        "details": {"error_code": "AUTH_401", "error_message": "Invalid credentials"},
        "suggested_actions": ["Reset your password"],
    }


class TicketModelTests(unittest.TestCase):
    def test_valid_json_parsing(self) -> None:
        ticket = HRSupportTicket.model_validate_json(json.dumps(ticket_data()))
        self.assertEqual(ticket.category, TicketCategory.AUTHENTICATION)
        self.assertEqual(ticket.priority, TicketPriority.MEDIUM)
        self.assertEqual(ticket.language, TicketLanguage.EN)
        self.assertEqual(ticket.details.error_code, "AUTH_401")
        self.assertEqual(ticket.model_dump(mode="json"), ticket_data())

    def test_invalid_enums_rejected(self) -> None:
        for field in ("category", "priority", "language"):
            with self.subTest(field=field):
                data = ticket_data()
                data[field] = "invalid"
                with self.assertRaises(ValidationError):
                    HRSupportTicket.model_validate(data)

    def test_every_top_level_field_required(self) -> None:
        for field in ticket_data():
            with self.subTest(field=field):
                data = ticket_data()
                del data[field]
                with self.assertRaises(ValidationError):
                    HRSupportTicket.model_validate(data)

    def test_every_nested_field_required(self) -> None:
        for field in ("error_code", "error_message"):
            with self.subTest(field=field):
                data = ticket_data()
                del data["details"][field]
                with self.assertRaises(ValidationError):
                    HRSupportTicket.model_validate(data)

    def test_nullable_fields_and_empty_actions(self) -> None:
        data = ticket_data()
        data.update(application=None, suggested_actions=[])
        data["details"] = {"error_code": None, "error_message": None}
        ticket = HRSupportTicket.model_validate_json(json.dumps(data))
        self.assertEqual(ticket.model_dump(mode="json"), data)

    def test_action_limit(self) -> None:
        for count in (0, 1, 3, 4):
            with self.subTest(count=count):
                data = ticket_data()
                data["suggested_actions"] = ["Check the portal"] * count
                if count <= 3:
                    self.assertEqual(
                        len(HRSupportTicket.model_validate(data).suggested_actions), count
                    )
                else:
                    with self.assertRaises(ValidationError):
                        HRSupportTicket.model_validate(data)

    def test_extra_fields_rejected(self) -> None:
        for nested in (False, True):
            with self.subTest(nested=nested):
                data = ticket_data()
                target = data["details"] if nested else data
                target["unexpected"] = "value"
                with self.assertRaises(ValidationError):
                    HRSupportTicket.model_validate(data)

    def test_string_and_boolean_types_not_coerced(self) -> None:
        for field, value in (("requires_support", "false"), ("summary", 123)):
            with self.subTest(field=field):
                data = ticket_data()
                data[field] = value
                with self.assertRaises(ValidationError):
                    HRSupportTicket.model_validate(data)

    def test_json_schema_requires_all_fields(self) -> None:
        schema = HRSupportTicket.model_json_schema()
        self.assertEqual(set(schema["required"]), set(ticket_data()))
        details = schema["$defs"]["TicketDetails"]
        self.assertEqual(set(details["required"]), {"error_code", "error_message"})
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(details["additionalProperties"])
        self.assertEqual(schema["properties"]["suggested_actions"]["maxItems"], 3)


if __name__ == "__main__":
    unittest.main()
