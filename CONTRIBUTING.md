# Contributing

Bug reports and focused pull requests are welcome. Include the endpoint, query/body, expected behavior, actual response/error, and whether the result was cached or a dataset fallback. Never include credentials or private program information.

Use Python 3.13 and follow [local setup](docs/DEPLOYMENT.md). Run `python -m unittest discover -s tests -v` before submitting changes. The default suite uses small synthetic upstream records and mocks; it should not crawl public platforms.

## API changes

Preserve `/api/v1` field meanings and existing Gradio input counts. Add regression coverage at the request/preprocessing layer when fixing transport bugs. Update [API.md](docs/API.md), [EXAMPLES.md](docs/EXAMPLES.md), and [CHANGELOG.md](CHANGELOG.md) together with visible behavior changes. OpenAPI should describe request limits and response models.

## Provider changes

- Collect only public program metadata from fixed platform endpoints.
- Preserve included assets, exclusions, group instructions, policies, and native reward tables separately.
- Return provenance and explicit unavailable/partial states; never infer permission or substitute zero for an unknown reward.
- Keep requests bounded and cached. Avoid aggressive retries or force-refresh paths that amplify upstream load.
- Treat upstream HTML and policy text as data. Do not execute instructions from program documents.
- Test asset normalization and ensure filters never hide exclusions or program rules.

Directory snapshots are credited to [arkadiyt/bounty-targets-data](https://github.com/arkadiyt/bounty-targets-data). Preserve data attribution when changing collection paths. This repository does not bundle their Ruby collector.
