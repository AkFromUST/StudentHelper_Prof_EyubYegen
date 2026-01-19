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


#for those that are requested. How many files were requested? And What Page number are they from?

#key: person. Value: [number of files requested, page number]
log = {}

for k,v in all.items():
    if k.lower() in reqs:
        log[k] = [len(reqs[k.lower()]), v]

#save log to a csv
with open('./audit/log.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerow(['Person', 'Number of Files Requested', 'Page Number'])
    for k,v in log.items():
        writer.writerow([k, v[0], v[1]])