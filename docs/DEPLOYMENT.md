# Development and deployment

## Local run

Python 3.13 is used by the hosted Space and CI.

```bash
git clone https://github.com/Wuhpondiscord/bbcollect.git
cd bbcollect
python -m venv .venv
```

Activate `.venv` (`.venv\Scripts\Activate.ps1` in PowerShell; `source .venv/bin/activate` on macOS/Linux), then:

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
python app.py
```

Gradio: `http://localhost:7860` · REST: `http://localhost:7860/api/v1` · Docs: `http://localhost:7860/api/docs`.

`app.py` mounts Gradio at `/` on the FastAPI application after registering REST routes, then starts Uvicorn. Keep the REST route registration before the root mount. No platform tokens or runtime secrets are needed. Set `PORT` to change port 7860.

## Hugging Face Space

The `README.md` front matter configures the Gradio Space with Python 3.13, Gradio 6.31.0, and `app_file: app.py`. Keep the Space public for anonymous access. Use CPU Basic unless your own load requires more resources; the app does not run a model.

GitHub Actions tests every push and pull request. Successful pushes to `main` and manual workflow dispatches upload application files to the existing `wuhp/bbconnectapi` Space. `scripts/deploy.py` explicitly selects app modules, docs, and examples; it never uploads secrets, `.git`, virtual environments, or tests, and does not mirror-delete unrelated Space files.

The GitHub Actions repository secret `HF_TOKEN` needs write access to the destination Space. **This secret is only for publishing. API callers do not need it, and the running application does not read it.** For a fork, change `repo_id` in `scripts/deploy.py`, add your own deployment secret, and update the public URLs in docs/examples.

## Public hosting behavior

- REST and Gradio are deliberately unauthenticated. Browser CORS allows public GET/POST calls without credentials.
- A per-process capacity gate permits two concurrent REST collection requests; busy callers get `429` with `Retry-After: 5`. Health/source descriptions stay lightweight.
- Source cache is process-local: 900 seconds for successes, 60 for failures. Multiple processes have independent caches/capacity gates. Use one Uvicorn process on the free Space.
- Free Spaces can sleep/restart. Long live scope requests may exceed a client's default timeout; start with small pages and allow a larger timeout. Summary discovery plus selected batch details is usually faster.
- There is no persistent storage, scheduled refresh, force-refresh bypass, service-level agreement, or API-key subscription mechanism.

## Release checklist

1. Run the test suite and verify generated OpenAPI schemas.
2. Keep the five-input Gradio `/collect` contract and six-input `/collect_options` contract intact.
3. Test `/api/v1/health`, `/api/docs`, a summary page, a detail document, normalized assets, and a mixed batch.
4. Confirm the Gradio UI and its event API still work after mounting.
5. Check `ok`, `partial`, and source states rather than treating missing rules as an empty policy.
6. Update the changelog, API reference, and examples for intentional behavior changes. Make breaking REST changes under a new versioned path.
