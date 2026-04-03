# Documentation Internationalization

This project publishes multilingual docs using MkDocs Material and the `mkdocs-static-i18n` plugin.

- Default locale (site default): `ko`
- Additional locales: `en` (and more as needed)
- Structure: `docs/<locale>/...` (e.g., `docs/ko/guides/...`, `docs/en/guides/...`)

## Add or Update a Translation

1) Add files under the target locale folder

- Mirror the Korean (canonical) file path: start from `docs/ko/guides/foo.md` and add `docs/en/guides/foo.md`.
- Keep headings consistent and use relative links.

2) Update navigation titles (optional)

- If the page appears in the MkDocs nav, ensure its title has a localized label.
- Add entries to `nav_translations` (under the `ko` config) when introducing new nav item titles.

3) Validate the docs build

- Run a full build locally:
  - `uv run mkdocs build`
- This validates both locales and catches missing or incorrect links.

4) Keep locale-incomplete drafts off-nav

- Reference-only drafts such as `design/icebox/*` should not be promoted into the official nav until the mirrored `ko`/`en` pair exists.
- List those pages in `mkdocs.yml` under `not_in_nav` so they are treated as intentionally unpublished rather than accidental navigation debt.
- Promote them into nav only after the pair is ready for the public information architecture.

5) Manage message catalogs (CLI translations)

- Install dev deps: `uv pip install -e .[dev]`
- Extract messages: `uv run pybabel extract -F babel.cfg -o qmtl/locale/qmtl.pot .`
- Initialize/update KO: `uv run pybabel init -l ko -i qmtl/locale/qmtl.pot -d qmtl/locale` (first time)
- Or update catalogs: `uv run pybabel update -l ko -i qmtl/locale/qmtl.pot -d qmtl/locale`
- Compile catalogs: `uv run pybabel compile -d qmtl/locale`

## Link Checking Policy

Our static link checker intentionally validates only the canonical (default) locale (ko) to avoid false positives from in‑progress translations:

- It reads the i18n configuration from `mkdocs.yml` and skips non‑default locales.
- Archived docs are also skipped.
- Intentionally off-nav drafts listed under `not_in_nav` are treated as explicit exceptions, not missing navigation entries.

Run it locally:

- `python scripts/check_docs_links.py`

## CLI Language Override

The CLI supports a language hint for user‑facing messages:

- Global option: `--lang {en,ko}` (e.g., `qmtl --lang ko project --help`)
- Environment variable: `QMTL_LANG=ko`

When no override is provided, the CLI attempts to detect a language from common locale environment variables and falls back to English.
