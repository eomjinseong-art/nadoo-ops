"""Open/update/close one GitHub issue per problem key (via gh CLI)."""
import json, subprocess

def _gh(*a, inp=None):
    return subprocess.run(["gh", *a], input=inp, capture_output=True, text=True, check=True).stdout

def open_issues(label):
    out = _gh("issue", "list", "--label", label, "--state", "open", "--limit", "200", "--json", "number,title")
    return {i["title"]: i["number"] for i in json.loads(out)}

def sync(label, problems):
    """problems: dict title -> body. Opens/updates those, closes other open issues with label."""
    subprocess.run(["gh", "label", "create", label, "--force", "--color", "d73a4a"], capture_output=True)
    cur = open_issues(label)
    for title, body in problems.items():
        if title in cur:
            _gh("issue", "comment", str(cur[title]), "--body-file", "-", inp="Still failing:\n\n" + body)
        else:
            _gh("issue", "create", "--label", label, "--title", title, "--body-file", "-", inp=body)
    for title, num in cur.items():
        if title not in problems:
            _gh("issue", "close", str(num), "--comment", "Resolved (no longer detected).")
