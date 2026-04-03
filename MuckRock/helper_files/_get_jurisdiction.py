import csv
import requests
from urllib.parse import urljoin

BASE_URL = "https://www.muckrock.com/api_v2/jurisdictions/"
OUTPUT_FILE = "../agencies_list/jurisdictions.csv"

def fetch_all_jurisdictions():
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
        all_rows.extend(results)

        next_url = data.get("next")
        if next_url and next_url.startswith("/"):
            next_url = urljoin("https://www.muckrock.com", next_url)

        url = next_url
        page_num += 1

    return all_rows

def write_csv(rows, output_file):
    if not rows:
        raise ValueError("No jurisdiction rows returned from API.")

    fieldnames = sorted({key for row in rows for key in row.keys()})

    with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def main():
    rows = fetch_all_jurisdictions()
    write_csv(rows, OUTPUT_FILE)
    print(f"Saved {len(rows)} jurisdictions to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()