"""
This script logs the number of files requested and the page number for each person requested. Does not show the missing people.
"""

#load json to a python dict
from collections import defaultdict
import json
import os
import csv

JSON_PATH = 'requested_documents.json'
PAGE_PATH = 'peopleToPage.json'

#data <> requested_documents.json
with open(JSON_PATH, 'r') as f:
    reqs = json.load(f)

#page_data <> peopleToPage.json
with open(PAGE_PATH, 'r') as f:
    all = json.load(f)


#key: person. Value: [number of files requested, page number]
log = {}

for k,v in all.items():
    if k.lower() in reqs:
        log[k] = [len(reqs[k.lower()]), v]

#save log to a csv
# with open('./audit/log.csv', 'w') as f:
#     writer = csv.writer(f)
#     writer.writerow(['Person', 'Number of Files Requested', 'Page Number'])
#     for k,v in log.items():
#         writer.writerow([k, v[0], v[1]])

#how many files have been requested? How Many people have been requested?
people_count = 0
files_count = 0

for k,v in log.items():
    people_count += 1
    files_count += v[0]

print(f"Total people requested: {people_count}")
print(f"Total files requested: {files_count}")