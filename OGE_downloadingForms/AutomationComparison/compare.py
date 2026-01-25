#compare the oge_people_their_total_files.json file with the target_folder_mapping.json file

import json
import csv
OGE_PEOPLE_THEIR_TOTAL_FILES_PATH = 'oge_people_their_total_files.json'
TARGET_FOLDER_MAPPING_PATH = 'target_folder_mapping.json'
TOTAL_REQS_PATH = '../requested_documents.json'

with open(OGE_PEOPLE_THEIR_TOTAL_FILES_PATH, 'r', encoding='utf-8') as f:
    oge_people_their_total_files = json.load(f)

with open(TARGET_FOLDER_MAPPING_PATH, 'r', encoding='utf-8') as f:
    target_folder_mapping = json.load(f)

with open(TOTAL_REQS_PATH, 'r', encoding='utf-8') as f:
    total_reqs = json.load(f)

remove_latest_people = [
    "Acker, Gerald",
    "Bedford, Bryan",
    "Brown, Thomas E",
    "Burgum, Douglas J",
    "Cabrera, Kevin M",
    "Candeub, Adam",
    "Chorle, Erhard R",
    "Dabbar, Paul M",
    "DeMarco, Vincent F",
    "Dowling, Maria-Kate",
    "Fuchs, Clinton",
    "Gaiser, Thomas",
    "Gil, Dario",
    "Gould, Jonathan",
    "Kenny, Stephen",
    "Mancini, Nadine N",
    "McKernan, Jonathan",
    "McMaster, Sean",
    "Morrison, Jonathan",
    "Theriot, Nicole D",
    "Trump, Donald J",
    "Walden, Paul A",
    "Wentworth, Lia"
]

# Gives the target folder mapping with the keys starting from the person name. Cleaned the key up basically.
def _clean_target_folder_mapping(target_folder_mapping):

    #We will clean the keys. We need to capture the key as follows
    #iterate through the key until "page" is seen. Then find the first "-" sign after "page". Then take the part after the "-" sign.

    res = {}
    for k,v in target_folder_mapping.items():
        #iterate through the key until "page" is seen. Then find the first "-" sign. Then take the part after the "-" sign.
        k = k.split("Page")
        if len(k) > 1:
            k = k[1]
        else:
            k = k[0]

        #if k has " - " then take the part after the "-" sign.
        if "-" in k:
            k = k.split("-")[1]
        else:
            k = k

        #remove all spaces from k
        k = k.replace(" ", "")
        k = k.lower()
        k = k.split(",")[0]
        k = k.replace(" ", "")
        k = k.lower()
        res[k] = v

    print("--------------------------------cleaned target folder mapping--------------------------------")
    return res

def _remove_latest_people(oge_people_their_total_files):
    #remove the people with the latest names
    for people in remove_latest_people:
        people = people.split(",")[0]
        people = people.replace(" ", "")
        people = people.lower()
        
        if people in oge_people_their_total_files:
            del oge_people_their_total_files[people]

    print("--------------------------------removed latest people--------------------------------")
    print(sum(oge_people_their_total_files.values()))
    print("--------------------------------")
    return oge_people_their_total_files

def compare_two_files(oge_people_their_total_files, cleaned_target_folder_mapping):
    stats = {}
    not_found_in_oge = {}
    not_found_in_target = {}
    total_files_found_in_student_dirs = 0

    for k,v in cleaned_target_folder_mapping.items():        
        if k not in oge_people_their_total_files:
            not_found_in_oge[k] = v
        else:
            stats[k] = oge_people_their_total_files[k] - v[0]
            total_files_found_in_student_dirs += v[0]

    for k,v in oge_people_their_total_files.items():
        if k not in cleaned_target_folder_mapping:
            not_found_in_target[k] = v

    return stats, not_found_in_oge, not_found_in_target, total_files_found_in_student_dirs


def map_to_student_RA(stats, cleaned_target_folder_mapping):
    res = {}
    no_student_mapping = []
    for k,v in stats.items():
        if k in cleaned_target_folder_mapping:
            res[cleaned_target_folder_mapping[k][1]] = v
        else:
            no_student_mapping.append(k)
    return res, no_student_mapping


def _double_check_name_matching(not_found_in_oge):
    #double check the name matching
    #get all keys
    total_files_found_in_student_dirs = 0
    all_reqs_keys = list(total_reqs.keys())
    not_found_in_all_reqs = []
    found_in_all_reqs_and_their_files_downloaded = {}
    found_in_all_reqs = []

    total_files_of_removed_people = 0

    for k,v in not_found_in_oge.items():
        not_found_in_all_reqs.append(k)
        for name in all_reqs_keys:
            if k.lower() in name:
                found_in_all_reqs.append(name)
                not_found_in_all_reqs.pop()
                found_in_all_reqs_and_their_files_downloaded[name] = v
                total_files_found_in_student_dirs += v[0]
                break
    
    for k,v in not_found_in_oge.items():
        if k in not_found_in_all_reqs:
            total_files_of_removed_people += v[0]


    print("People found in all reqs keys: ", len(found_in_all_reqs))
    print("People not found in all reqs keys: ", len(not_found_in_all_reqs))
    print("Total files of removed people: ", total_files_of_removed_people)
    print("--------------------------------")

    print(found_in_all_reqs)
    print(not_found_in_all_reqs)
    print("--------------------------------")

    return found_in_all_reqs, not_found_in_all_reqs, found_in_all_reqs_and_their_files_downloaded, total_files_found_in_student_dirs

cleaned_target_folder_mapping = _clean_target_folder_mapping(target_folder_mapping)
cleaned_oge_people_their_total_files = _remove_latest_people(oge_people_their_total_files)
stats,not_found_in_oge, not_found_in_target, total_files_found_in_student_dirs_before = compare_two_files(cleaned_oge_people_their_total_files, cleaned_target_folder_mapping)
student_RA, no_student_mapping = map_to_student_RA(stats, cleaned_target_folder_mapping)
found_in_all_reqs, not_found_in_all_reqs, found_in_all_reqs_and_their_files_downloaded, total_files_found_in_student_dirs_after = _double_check_name_matching(not_found_in_oge)

#print(student_RA)
print("--------------------------------")

print("Total files found in student dirs after second matching:  ", total_files_found_in_student_dirs_after)
print("Total files found in student dirs before second matching:  ", total_files_found_in_student_dirs_before)
print("Total files found in student dirs:  ", total_files_found_in_student_dirs_after + total_files_found_in_student_dirs_before)
print("--------------------------------")


#save the results to a json file
FINALRESULTPATH = "results/comparison_results.json"
with open(FINALRESULTPATH, 'w', encoding='utf-8') as f:
    json.dump(student_RA, f, indent=2, ensure_ascii=False)

NOTFOUNDINOGEPATH = "results/not_found_in_oge.json"
with open(NOTFOUNDINOGEPATH, 'w', encoding='utf-8') as f:
    json.dump(not_found_in_oge, f, indent=2, ensure_ascii=False)

NOTFOUNDINTARGETPATH = "results/not_found_in_target.json"
with open(NOTFOUNDINTARGETPATH, 'w', encoding='utf-8') as f:
    json.dump(not_found_in_target, f, indent=2, ensure_ascii=False)

FOUND_IN_ALL_REQS_AND_THEIR_FILES_DOWNLOADED_PATH = "results/found_in_all_reqs_and_their_files_downloaded.json"
with open(FOUND_IN_ALL_REQS_AND_THEIR_FILES_DOWNLOADED_PATH, 'w', encoding='utf-8') as f:
    json.dump(found_in_all_reqs_and_their_files_downloaded, f, indent=2, ensure_ascii=False)

#this needs to be a csv file. not_found_in_all_reqs is a list of names.
NOTFOUNDINALLREQSPATH = "results/not_found_in_all_reqs.csv"
with open(NOTFOUNDINALLREQSPATH, 'w', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(["Name"])
    for name in not_found_in_all_reqs:
        writer.writerow([name])
