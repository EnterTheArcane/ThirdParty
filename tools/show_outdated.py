"""Parse check_updates.py JSON output."""
import subprocess, sys, json

result = subprocess.run(
    [sys.executable, "tools/check_updates.py", "--outdated-only", "--json"],
    capture_output=True, text=True, cwd="."
)
data = json.loads(result.stdout)
for d in data:
    if d.get("status") == "outdated":
        print(f"{d['name']}|{d['version']}|{d['latest_tag']}")
