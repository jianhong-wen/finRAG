"""List metadata of all datasets in the City of Toronto Open Data portal (CKAN).

Usage:
    python3 -I list_toronto_datasets.py OUTPUT.csv [KEYWORD ...]

Writes one row per dataset. If keywords are given, only datasets whose title,
name, notes or tags contain at least one keyword (case-insensitive) are kept.
"""

import csv
import json
import sys
import urllib.parse
import urllib.request

BASE = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action"
PAGE_SIZE = 100


def call(action, **params):
    url = f"{BASE}/{action}?{urllib.parse.urlencode(params)}"
    if not url.startswith("https://"):
        raise ValueError(f"Refusing non-HTTPS URL: {url}")
    # URL is built from the fixed HTTPS base above.
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
        payload = json.load(response)
    if not payload.get("success"):
        raise RuntimeError(f"CKAN call failed: {url}")
    return payload["result"]


def fetch_all():
    start = 0
    while True:
        result = call("package_search", rows=PAGE_SIZE, start=start)
        packages = result["results"]
        if not packages:
            return
        yield from packages
        start += len(packages)
        if start >= result["count"]:
            return


def to_row(pkg):
    resources = pkg.get("resources", [])
    formats = sorted({r.get("format", "") for r in resources if r.get("format")})
    datastore = any(r.get("datastore_active") for r in resources)
    return {
        "name": pkg.get("name", ""),
        "title": pkg.get("title", ""),
        "division": (pkg.get("owner_division") or ""),
        "refresh_rate": pkg.get("refresh_rate", ""),
        "formats": ";".join(formats),
        "datastore_active": datastore,
        "last_refreshed": pkg.get("last_refreshed", ""),
        "tags": ";".join(t.get("name", "") for t in pkg.get("tags", [])),
        "url": f"https://open.toronto.ca/dataset/{pkg.get('name', '')}/",
        "notes": " ".join((pkg.get("notes") or "").split())[:300],
    }


def matches(row, keywords):
    if not keywords:
        return True
    text = " ".join([row["title"], row["name"], row["notes"], row["tags"]]).lower()
    return any(k.lower() in text for k in keywords)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    output, keywords = sys.argv[1], sys.argv[2:]
    rows = [r for r in map(to_row, fetch_all()) if matches(r, keywords)]
    if not rows:
        sys.exit("No datasets matched.")
    with open(output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} datasets to {output}")


if __name__ == "__main__":
    main()
