"""Maintain one GitHub Issue for actionable import and expiry warnings."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

TITLE = "[Speiseplan] Import oder Folgeplan prüfen"
WARNINGS = Path(__file__).resolve().parents[1] / "import-warnings.json"


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        raise RuntimeError("GitHub-Token bzw. Repository fehlt")
    if not WARNINGS.exists():
        warnings = ["Import wurde vor Erstellung des Warnberichts abgebrochen; Actions-Log prüfen."]
    else:
        warnings = json.loads(WARNINGS.read_text(encoding="utf-8")).get("warnings", [])
    if os.environ.get("UPDATE_OUTCOME") != "success":
        warnings.append("Import-Workflow fehlgeschlagen; Actions-Log prüfen.")
    if os.environ.get("COMMIT_OUTCOME") == "failure":
        warnings.append("Neue Daten konnten nicht ins Repository geschrieben werden; Actions-Log prüfen.")
    base = f"https://api.github.com/repos/{repo}/issues"

    def api(url: str, method: str = "GET", value: dict | None = None):
        data = json.dumps(value).encode("utf-8") if value is not None else None
        request = Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "school-menu-import",
            **({"Content-Type": "application/json"} if data is not None else {}),
        })
        with urlopen(request, timeout=20) as response:
            return json.load(response)

    existing = next((issue for issue in api(base + "?state=open&per_page=100")
                     if issue.get("title") == TITLE and "pull_request" not in issue), None)
    if warnings:
        body = ("Der automatische Speiseplan-Import benötigt Aufmerksamkeit. "
                "Bitte Schul-PDF und Actions-Log prüfen; keine Gerichte erraten.\n\n"
                + "\n".join("- " + warning for warning in warnings)
                + "\n\n[Workflow-Läufe](https://github.com/" + quote(repo, safe="/")
                + "/actions/workflows/update-menu.yml)\n")
        if existing:
            if existing.get("body") != body:
                api(existing["url"], "PATCH", {"body": body})
        else:
            api(base, "POST", {"title": TITLE, "body": body})
    elif existing:
        api(existing["url"], "PATCH", {"state": "closed",
                                       "state_reason": "completed"})


if __name__ == "__main__":
    main()
