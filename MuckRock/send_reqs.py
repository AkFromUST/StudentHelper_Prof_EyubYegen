from config import USERNAME, PASSWORD, ORGANIZATION_ID, TITLE, REQS_DOCS
import pandas as pd
import time
from typing import Iterable, Optional
import requests
import csv
from pathlib import Path

ACCOUNTS_TOKEN_URL = "https://accounts.muckrock.com/api/token/"
BASE_URL = "https://www.muckrock.com/api_v2"
REQS_ID_PATH = "./agencies_list/police_dept_reqs_ids.csv"

# get the list of agencies from the csv file
def _get_agencies_list(path_to_csv):
    df = pd.read_csv(path_to_csv)
    return df['muckrock_id'].tolist()

# get the jwt_tokens
def _get_jwt_token(username: str, password: str) -> str:
    payload = {"username": username, "password": password}

    resp = requests.post(ACCOUNTS_TOKEN_URL, json=payload, timeout=30)

    if resp.status_code >= 400:
        resp = requests.post(ACCOUNTS_TOKEN_URL, data=payload, timeout=30)

    resp.raise_for_status()
    data = resp.json()

    access = data.get("access")
    if not access:
        raise ValueError(f"No access token in response: {data}")

    return access

# submit the reqs. Store the reqs_id in a .csv file
def submit_foi_requests_to_csv(
    agency_ids: Iterable[int],
    title: str,
    requested_docs: str,
    jwt_token: str,
    organization: Optional[int] = None,
    embargo_status: str = "embargo",
    csv_path: str = REQS_ID_PATH,
):
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    # Ensure directories exist
    csv_file = Path(csv_path)
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_file.exists()

    rows = []

    with open(csv_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if write_header:
            writer.writerow(["agency_id", "request_id"])

        for agency_id in agency_ids:
            payload = {
                "agencies": [int(agency_id)],
                "title": title,
                "requested_docs": requested_docs,
                "embargo_status": embargo_status,
            }
            
            if organization is not None:
                payload["organization"] = int(organization)

            resp = requests.post(
                f"{BASE_URL}/requests/",
                headers=headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            # MuckRock returns {"location": "/foi/agency-slug/title-slug-ID/"}
            # We extract the ID from the end of the URL string.
            location_url = data.get("location", "")
            try:
                request_id = int(location_url.strip("/").split("-")[-1])
            except (ValueError, IndexError):
                request_id = location_url  # Fallback to saving the raw URL if extraction fails
                
            writer.writerow([agency_id, request_id])
            rows.append({"agency_id": int(agency_id), "request_id": request_id})

    return rows


agency_ids = _get_agencies_list("agencies_list/police_dept_muckrock_ids.csv")
jwt_token = _get_jwt_token(USERNAME, PASSWORD)
# rows = submit_foi_requests_to_csv(agency_ids, TITLE, REQS_DOCS, jwt_token, ORGANIZATION_ID, "embargo", REQS_ID_PATH)
# print(rows)


def _find_individual_request_id(
    agency_id: int,
    title: str,
    jwt_token: str,
    retries: int = 5,
    delay_seconds: int = 2,
) -> int:
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/json",
    }

    for _ in range(retries):
        resp = requests.get(
            f"{BASE_URL}/requests/",
            headers=headers,
            params={
                "agency": int(agency_id),
                "ordering": "-datetime_submitted",
                "page_size": 10,
            },
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

        for req in results:
            if req.get("title") == title:
                return req["id"]

        time.sleep(delay_seconds)

    raise ValueError(
        f"Could not find individual request_id for agency_id={agency_id} and title={title!r}"
    )


def submit_foi_requests_to_csv_2(
    agency_ids: Iterable[int],
    title: str,
    requested_docs: str,
    jwt_token: str,
    organization: Optional[int] = None,
    embargo_status: str = "embargo",
    csv_path: str = REQS_ID_PATH,
):

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    csv_file = Path(csv_path)
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_file.exists()

    rows = []

    with open(csv_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if write_header:
            writer.writerow(["agency_id", "request_id"])

        for agency_id in agency_ids:
            payload = {
                "agencies": [int(agency_id)],
                "title": title,
                "requested_docs": requested_docs,
                "embargo_status": embargo_status,
            }

            if organization is not None:
                payload["organization"] = int(organization)

            post_resp = requests.post(
                f"{BASE_URL}/requests/",
                headers=headers,
                json=payload,
                timeout=30,
            )
            post_resp.raise_for_status()

            individual_request_id = _find_individual_request_id(
                agency_id=agency_id,
                title=title,
                jwt_token=jwt_token,
            )

            writer.writerow([agency_id, individual_request_id])
            rows.append({
                "agency_id": int(agency_id),
                "request_id": individual_request_id,
            })

    return rows


def test_lookup_individual_request_id(agency_id: int, title: str, jwt_token: str):
    request_id = _find_individual_request_id(
        agency_id=agency_id,
        title=title,
        jwt_token=jwt_token,
        retries=1,
        delay_seconds=0,
    )
    print(f"agency_id={agency_id}, request_id={request_id}")
    return request_id

jwt_token = _get_jwt_token(USERNAME, PASSWORD)

test_lookup_individual_request_id(
    agency_id=3523,
    title="Request for Annual Totals of FOIA Requests Received",
    jwt_token=jwt_token,
)