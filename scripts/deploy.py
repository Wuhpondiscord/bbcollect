"""Deploy only application files; never upload credentials or mirror-delete the Space."""
import os
from pathlib import Path
from huggingface_hub import HfApi

if not os.environ.get("HF_TOKEN"):
    raise SystemExit("Set the GitHub Actions repository secret HF_TOKEN with write access to wuhp/bbconnectapi")

root = Path(__file__).resolve().parents[1]
api = HfApi(token=os.environ["HF_TOKEN"])
api.upload_folder(
    repo_id="wuhp/bbconnectapi", repo_type="space", folder_path=str(root),
    allow_patterns=["app.py", "api.py", "collector.py", "details.py", "requirements.txt", "README.md", "docs/**", "examples/**"],
    commit_message="Deploy bbcollect " + os.environ.get("GITHUB_SHA", "manual"),
)
print("Deployed application to https://huggingface.co/spaces/wuhp/bbconnectapi")
