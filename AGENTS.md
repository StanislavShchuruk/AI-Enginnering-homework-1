# Project instructions

- Read docs/PROJECT_CONTEXT.md for the project scope and agreed schema.
- Use Python 3.11+ and Pydantic v2.
- Keep the architecture simple, modular, and testable.
- Prefer clear, readable code over unnecessary abstractions.
- Use type hints.
- Never hardcode API keys or secrets.
- Keep prompts versioned separately from application code.
- Do not introduce unnecessary dependencies.
- Add tests for important validation logic. Existing schema tests use unittest;
  dataset validation uses pytest. Run python -m pytest to execute both.
- Do not implement functionality outside the current task unless requested.
- Never read or display .env or .env.* files, except .env.example.
- Use .env.example to discover configuration variable names.
- Never print secrets or inspect environment variables to retrieve credentials.
- Never make real API calls or run tests that incur costs without explicit user approval.
