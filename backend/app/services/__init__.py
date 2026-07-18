"""Service layer — the application's use-cases.

Each service holds the orchestration that used to live in route handlers:
validation, sequencing across repositories, versioning, LLM calls. Services are
**HTTP-agnostic** — they raise the domain errors in `errors.py`, which a single
exception handler (registered in `main.create_app`) maps to status codes. That
keeps controllers thin (parse → call service → return) and lets services be
unit-tested without spinning up the web stack.
"""
