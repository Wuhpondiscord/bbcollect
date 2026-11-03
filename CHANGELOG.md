# Changelog

## 1.0.0 · 2026-11-03

- Added a public REST API under `/api/v1` with no key/login requirement and browser CORS.
- Added interactive documentation at `/api/docs`, ReDoc at `/api/redoc`, and a machine-readable OpenAPI schema at `/api/openapi.json`.
- Added summary search, currency-aware reward filters/sorting, pagination, full detail pages, and batches of up to 20 programs.
- Added normalized asset records while retaining native records, program rules, and every exclusion.
- Added application readiness, source capability descriptions, directory statistics, structured errors, and busy/retry responses.
- Added Python/JavaScript/curl recipes, a paginated JSON/CSV export example, deployment guidance, and contribution documentation.
- Preserved existing Gradio APIs: `/collect` takes five inputs; `/collect_options` takes six; `/details`, `/scope`, and `/sources` remain available.

## Earlier updates · 2026-11-03

- Added live HackerOne program listings and public directory feeds for Bugcrowd, Intigriti, and YesWeHack.
- Added live detail collectors for reward ranges/tables, full scopes, and program policies on all four platforms.
- Corrected Intigriti identifiers for programs sharing a URL slug across companies.
- Restored five-input Gradio compatibility after introducing the optional details toggle.
