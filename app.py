"""Gradio UI and named JSON API endpoints for bbcollect."""
import os

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr
from collector import PLATFORMS, collector


def collect(platforms, search, bounty_only, limit, offset):
    """Stable five-input API; always include live rewards, scopes and rules."""
    return collector.collect(platforms, search, bounty_only, limit, offset, True)


def collect_options(platforms, search, bounty_only, limit, offset, include_details=True):
    """Collect programs with an explicit full-details/summary toggle."""
    return collector.collect(platforms, search, bounty_only, limit, offset, include_details)


def scope(platform, handle):
    """Fetch scopes, rules and rewards for a program (alias of /details)."""
    return collector.scope(platform, handle.strip())


def details(platform, handle):
    """Get live public rewards, scopes, exclusions and full program rules."""
    return collector.details(platform, handle.strip())


def sources():
    """Describe supported sources and cache behavior without crawling upstreams."""
    return {"platforms": list(PLATFORMS), "hackerone": "Public live GraphQL, dataset fallback",
            "other_platforms": "Directory: public dataset; details: live platform public program documents",
            "collect_default": "Five inputs; full details, scopes, rules and reward tables",
            "collect_options": "Six inputs; include_details=False for summaries",
            "cache_seconds": 900, "failure_cache_seconds": 60,
            "scope_fields": "Platform-native fields; in_scope and out_of_scope kept separate"}


with gr.Blocks(title="bbconnectapi") as demo:
    gr.Markdown("# bbconnectapi\nPublic bug bounty programs and scope, available as a JSON API. "
                "HackerOne uses live public data with an explicit dataset fallback. "
                "All four platforms have live program details: reward tables, scopes and rules. "
                "Directory feeds use public snapshots outside HackerOne. Results are cached for 15 minutes.")
    with gr.Tab("Programs"):
        platforms = gr.CheckboxGroup(list(PLATFORMS), value=["hackerone"], label="Platforms")
        search = gr.Textbox(label="Search name, handle, URL or website", max_lines=1)
        bounty_only = gr.Checkbox(label="Only programs known to offer bounties", value=False)
        include_details = gr.Checkbox(label="Include scopes, rules and live reward tables (slower)", value=True)
        with gr.Row():
            limit = gr.Slider(1, 100, value=10, step=1, label="Page size")
            offset = gr.Number(value=0, precision=0, minimum=0, maximum=100000, label="Offset")
        collect_button = gr.Button("Collect programs", variant="primary")
        programs_json = gr.JSON(label="Programs and source status")
        collect_button.click(collect_options, [platforms, search, bounty_only, limit, offset, include_details],
                             programs_json, api_name="collect_options", concurrency_limit=2)
        # Preserve the original wire format: Gradio validates component counts
        # before Python defaults apply, so /collect must have exactly five inputs.
        legacy_collect = gr.Button(visible=False)
        legacy_collect.click(collect, [platforms, search, bounty_only, limit, offset],
                             programs_json, api_name="collect", concurrency_limit=2)
    with gr.Tab("Program details and scope"):
        platform = gr.Dropdown(list(PLATFORMS), value="hackerone", label="Platform")
        handle = gr.Textbox(value="security", label="Program handle (from collect results)")
        scope_button = gr.Button("Get rewards, scopes and rules")
        scope_json = gr.JSON(label="Rewards, targets, rules and source status")
        scope_button.click(scope, [platform, handle], scope_json, api_name="scope", concurrency_limit=2)
        details_button = gr.Button("Get full details via /details")
        details_button.click(details, [platform, handle], scope_json, api_name="details", concurrency_limit=2)
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
