"""
    Read through the direct_downloads folder and generate a mapping of the person (folder name) to the number of files are present in that folder.  
"""

import os
import json

DIRECT_DOWNLOADS_PATH = "direct_downloads"

#get all the folders in the direct_downloads folder
person_folders = os.listdir(DIRECT_DOWNLOADS_PATH)

#generate a mapping of the person (folder name) to the number of files are present in that folder
person_files_mapping = {}

for folder in person_folders:
    files = os.listdir(os.path.join(DIRECT_DOWNLOADS_PATH, folder))
    person_files_mapping[folder] = len(files)

#save the mapping to a json file
with open('direct_downloads_person_mapping.json', 'w') as f:
    json.dump(person_files_mapping, f, indent=2, ensure_ascii=False)