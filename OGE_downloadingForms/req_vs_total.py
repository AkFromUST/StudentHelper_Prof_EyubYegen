#load json to a python dict
from collections import defaultdict
import json
import os

JSON_PATH = 'requested_documents.json'
PAGE_PATH = 'peopleToPage.json'

#data <> requested_documents.json
with open(JSON_PATH, 'r') as f:
    reqs = json.load(f)

#page_data <> peopleToPage.json
with open(PAGE_PATH, 'r') as f:
    all = json.load(f)


audit = {}
missing_people_pages = []
missing_people_pages_count = {}

for k, v in all.items():
    if k.lower() not in reqs:
        audit[k] = v
        missing_people_pages.append(v)
        if v in missing_people_pages_count:
            missing_people_pages_count[v] += 1
        else:
            missing_people_pages_count[v] = 1

print("People not requested and their page numbers")
print("=" * 100)
print("\n")
for k, v in audit.items():
    print(f"{k}: {v}")
print("\n")
print("=" * 100)

print("Total people not requested: ", len(audit.keys()))


total_missing_rows = sum(missing_people_pages_count.values())

print(missing_people_pages_count)

#find the halway point of the total_missing_rows
halfway_point = total_missing_rows / 3

#find the page number that is closest to the halfway point
closest_page = []
window_sum = 0
closest_page_count = 0
for k, v in missing_people_pages_count.items():
    window_sum += v
    if window_sum > halfway_point:
        closest_page.append(k)
        window_sum = 0

print(closest_page)