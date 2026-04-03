import csv
import requests
from urllib.parse import urljoin

BASE_URL = "https://www.muckrock.com/api_v2/agencies/"
OUTPUT_FILE = "../agencies_list/agencies.csv"

def flatten_dict(d, parent_key="", sep="."):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            if all(isinstance(x, dict) for x in v):
                items.append((new_key, str(v)))
            else:
                items.append((new_key, "|".join("" if x is None else str(x) for x in v)))
        else:
            items.append((new_key, v))
    return dict(items)

def fetch_all_agencies():
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    })

    url = BASE_URL
    all_rows = []
    page_num = 1

    while url:
        print(f"Fetching page {page_num}: {url}")
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        for row in results:
            all_rows.append(flatten_dict(row))

        next_url = data.get("next")
        if next_url and next_url.startswith("/"):
            next_url = urljoin("https://www.muckrock.com", next_url)

        url = next_url
        page_num += 1

    return all_rows

def write_csv(rows, output_file):
    if not rows:
        raise ValueError("No agency rows returned from API.")

    fieldnames = sorted({key for row in rows for key in row.keys()})

    with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def main():
    rows = fetch_all_agencies()
    write_csv(rows, OUTPUT_FILE)
    print(f"Saved {len(rows)} agencies to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()