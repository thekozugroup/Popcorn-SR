Commit and push as thekozugroup@gmail.com. No AI co-author tags.
Keep replies concise; explain the user impact before technical detail.
Keep main as the session-end source of truth. Commit only intended files.
Read PRODUCT.md before design work. Use installed Taste and Impeccable skills during design and review.
Show actual rendered UI previews periodically during frontend work. Label simulated hardware states.
Run `uv run ruff check .`, `uv run pytest`, `npm run build`, and the Docker smoke test before shipping.
Prefer local builds and tests. Keep GitHub workflows manual; use them only when local execution is unavailable and the user requests the fallback.
Never overwrite library originals. Never claim GPU/AI support from a device name or a mock test.
Record current scope and evidence in working.md. No credentials or local media in commits.
Use the existing signed-in Chrome profile for interactive UI checks; do not use a blank profile.
