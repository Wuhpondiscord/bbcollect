"""Gradio UI and named JSON API endpoints for bbcollect."""
import os

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr
from collector import PLATFORMS, collector


def collect(platforms, search, bounty_only, limit, offset):
    """List public programs with filters, pagination and per-source provenance."""
    return collector.collect(platforms, search, bounty_only, limit, offset)


def scope(platform, handle):
    """Fetch public in-scope and out-of-scope assets for a program handle."""
    return collector.scope(platform, handle.strip())


def sources():
    """Describe supported sources and cache behavior without crawling upstreams."""
    return {"platforms": list(PLATFORMS), "hackerone": "Public live GraphQL, dataset fallback",
            "other_platforms": "arkadiyt/bounty-targets-data public snapshots",
            "cache_seconds": 900, "failure_cache_seconds": 60,
            "scope_fields": "Platform-native fields; in_scope and out_of_scope kept separate"}


with gr.Blocks(title="bbconnectapi") as demo:
    gr.Markdown("# bbconnectapi\nPublic bug bounty programs and scope, available as a JSON API. "
                "HackerOne uses live public data with an explicit dataset fallback. "
                "Other platforms use public dataset snapshots. Results are cached for 15 minutes.")
    with gr.Tab("Programs"):
        platforms = gr.CheckboxGroup(list(PLATFORMS), value=["hackerone"], label="Platforms")
        search = gr.Textbox(label="Search name, handle, URL or website", max_lines=1)
        bounty_only = gr.Checkbox(label="Only programs known to offer bounties", value=False)
        with gr.Row():
            limit = gr.Slider(1, 1000, value=100, step=1, label="Page size")
            offset = gr.Number(value=0, precision=0, minimum=0, maximum=100000, label="Offset")
        collect_button = gr.Button("Collect programs", variant="primary")
        programs_json = gr.JSON(label="Programs and source status")
        collect_button.click(collect, [platforms, search, bounty_only, limit, offset],
                             programs_json, api_name="collect", concurrency_limit=2)
    with gr.Tab("Program scope"):
        platform = gr.Dropdown(list(PLATFORMS), value="hackerone", label="Platform")
        handle = gr.Textbox(value="security", label="Program handle (from collect results)")
        scope_button = gr.Button("Get scope")
        scope_json = gr.JSON(label="Scope and source status")
        scope_button.click(scope, [platform, handle], scope_json, api_name="scope", concurrency_limit=2)
    with gr.Tab("API"):
        gr.Markdown('''Use **View API** in the footer for generated client examples.

```python
from gradio_client import Client
client = Client("wuhp/bbconnectapi")
result = client.predict(
    platforms=["hackerone", "bugcrowd"], search="", bounty_only=False,
    limit=100, offset=0, api_name="/collect")
scope = client.predict(platform="hackerone", handle="security", api_name="/scope")
```

Scope is a snapshot: check the linked program's current rules and exclusions before testing.''')
        source_button = gr.Button("Source information")
        source_json = gr.JSON(label="Supported sources")
        source_button.click(sources, [], source_json, api_name="sources")

demo.queue(max_size=32, default_concurrency_limit=2)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.getenv("PORT", "7860")),
                show_error=False)
