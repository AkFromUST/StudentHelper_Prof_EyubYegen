#load json to a python dict
from collections import defaultdict
import json
import os

JSON_PATH = 'requested_documents.json'

with open(JSON_PATH, 'r') as f:
    data = json.load(f)

total_files = defaultdict(int)

for k, v in data.items():
    #take the k until the first comma
    name = k.split(',')[0].strip()
    total_files[name] += len(v)
    
#now lets get the actual files stored in the directory

cwd = os.getcwd()

dir_files = defaultdict(int)
dir_names = [cwd + "/OGE_Documents/RA_Collection_Aarav_Kumar_Page_37", cwd + "/OGE_Documents/RA_Collection_Aarav_Kumar_Page_38", cwd + "/OGE_Documents/RA_Collection_Kumar_Aarav_Page_39"]

total_d = 0
for dir in dir_names:
    for file in os.listdir(dir):
        #get the name of the file until the first comma
        name = file.split(',')[0].strip()
        
        if name == ".DS_Store":
            continue
        
        #now get the number of files in the dir
        dir_files[name.lower()] += len(os.listdir(dir + "/" + file))
        total_d += len(os.listdir(dir + "/" + file))

unknown_names = []
missing_files = defaultdict(int)
missing_names = defaultdict(int)

#now lets compare dir_files with total_files
for name, files in dir_files.items():

    if name not in total_files:
        unknown_names.append(name)
        continue

    if total_files[name] > files:
        missing_files[name] += total_files[name] - files


for name, files in total_files.items():
    if name not in dir_files:
        missing_names[name] += files

total = sum(total_files.values())

print("=" * 100)
print("Unknown Names. Names that are not present in requested_documents.json but are present in the directory. These should not exist:")
print(unknown_names)
print("=" * 100)

print("\n"*5)
print("=" * 100)
print("These are files that are yet to be recieved from OGE:")
print(missing_files)
print("To Make your life easier, just copy the below")
for k, v in missing_files.items():
    print(f"{k}")

for k, v in missing_files.items():
    print(f"{v}")
print("=" * 100)

print("\n"*5)
print("=" * 100)
print("These are names that are present in requested_documents.json but are not present in the directory. These should exist:")
for k, v in missing_names.items():
    print(f"{k}: {v}")
print("To Make your life easier, just copy the below")
for k, v in missing_names.items():
    print(f"{k}")

for k, v in missing_names.items():
    print(f"{v}")

print("=" * 100)
    
print(total)
print(total_d)