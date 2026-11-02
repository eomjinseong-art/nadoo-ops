"""Health check: failed GitHub Actions runs (26h) across owner repos + Vercel prod deployment state."""
import datetime as dt, json, os, sys, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(__file__))
import issues

OWNER = os.environ.get("GH_OWNER", "eomjinseong-art")
TEAM = os.environ.get("VERCEL_TEAM", "mate13")
SELF = os.environ.get("GITHUB_REPOSITORY", "")
since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=26)

def get(url, headers, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code < 500 or i == tries - 1: raise
        except Exception:
            if i == tries - 1: raise
        time.sleep(3 * (i + 1))

gh_h = {"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json"}
problems, errors = {}, []

repos, page = [], 1
while True:
    r = get(f"https://api.github.com/users/{OWNER}/repos?per_page=100&page={page}&type=owner", gh_h)
    repos += r
    if len(r) < 100: break
    page += 1
for repo in repos:
    if repo.get("archived"): continue
    full = repo["full_name"]
    try:
        runs = get(f"https://api.github.com/repos/{full}/actions/runs?per_page=100&created=>={since:%Y-%m-%dT%H:%M:%SZ}", gh_h).get("workflow_runs", [])
    except Exception as e:
        errors.append(f"{full}: {e}"); continue
    latest = {}
    for run in runs:  # newest first; judge each workflow by its latest completed run
        if run["status"] != "completed": continue
        latest.setdefault(run["name"], run)
    for name, run in latest.items():
        if run["conclusion"] in ("failure", "timed_out", "startup_failure"):
            if full == SELF and name == "health": continue
            problems[f"[health] Actions failing: {full} / {name}"] = (
                f"Latest run concluded **{run['conclusion']}** at {run['updated_at']}.\n\n{run['html_url']}")

vt = os.environ.get("VERCEL_TOKEN")
if not vt:
    problems["[health] VERCEL_TOKEN secret missing"] = "Set the VERCEL_TOKEN repo secret."
else:
    vh = {"Authorization": f"Bearer {vt}"}
    try:
        projs, nxt = [], None
        while True:
            q = f"https://api.vercel.com/v9/projects?slug={TEAM}&limit=100" + (f"&until={nxt}" if nxt else "")
            d = get(q, vh); projs += d["projects"]; nxt = d.get("pagination", {}).get("next")
            if not nxt: break
        for p in projs:
            try:
                d = get(f"https://api.vercel.com/v6/deployments?slug={TEAM}&projectId={p['id']}&target=production&limit=1", vh, tries=6)
            except urllib.error.HTTPError:
                raise
            except Exception as e:
                errors.append(f"vercel {p['name']}: {e}"); continue
            deps = d.get("deployments", [])
            if not deps: continue
            st = deps[0].get("state") or deps[0].get("readyState")
            if st in ("ERROR", "CANCELED"):
                problems[f"[health] Vercel production {st}: {p['name']}"] = (
                    f"Latest production deployment state **{st}**: https://{deps[0].get('url')}\n"
                    f"https://vercel.com/{TEAM}/{p['name']}")
        print(f"vercel projects checked: {len(projs)}")
    except urllib.error.HTTPError as e:
        problems["[health] Vercel API error"] = f"Vercel API returned HTTP {e.code}. Check VERCEL_TOKEN."
    except Exception as e:
        errors.append(f"vercel: {e}")

print(f"repos checked: {len(repos)}; problems: {len(problems)}")
for t in problems: print(" -", t)
for e in errors: print(" warn:", e)
if os.environ.get("DRY"): sys.exit(0)
issues.sync("health", problems)
