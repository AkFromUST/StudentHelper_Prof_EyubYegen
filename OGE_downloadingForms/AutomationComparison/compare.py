#compare the oge_people_their_total_files.json file with the target_folder_mapping.json file

import json

OGE_PEOPLE_THEIR_TOTAL_FILES_PATH = 'oge_people_their_total_files.json'
TARGET_FOLDER_MAPPING_PATH = 'target_folder_mapping.json'

with open(OGE_PEOPLE_THEIR_TOTAL_FILES_PATH, 'r', encoding='utf-8') as f:
    oge_people_their_total_files = json.load(f)

with open(TARGET_FOLDER_MAPPING_PATH, 'r', encoding='utf-8') as f:
    target_folder_mapping = json.load(f)

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
    print(res)
    print("--------------------------------")
    return res

def _clean_oge_people_their_total_files(oge_people_their_total_files):
    #clean the keys
    res = {}
    for k,v in oge_people_their_total_files.items():
        k = k.split(",")[0]
        k = k.replace(" ", "")
        k = k.lower()
        res[k] = v

    print("--------------------------------cleaned oge people their total files--------------------------------")
    print(res)
    print("--------------------------------")
    return res



def compare_two_files(oge_people_their_total_files, cleaned_target_folder_mapping):
    stats = {}
    not_found_in_oge = {}
    not_found_in_target = {}

    for k,v in cleaned_target_folder_mapping.items():
        #clean k
        k = k.split(",")[0]
        k = k.replace(" ", "")
        k = k.lower()
        
        if k not in oge_people_their_total_files:
            not_found_in_oge[k] = v
        else:
            stats[k] = oge_people_their_total_files[k] - v[0]
            if stats[k] < 0:
                print("Negative stats found for ", k)
                print("\tOGE: ", oge_people_their_total_files[k])
                print("\tTarget: ", v[0])
        
    for k,v in oge_people_their_total_files.items():
        if k not in cleaned_target_folder_mapping:
            not_found_in_target[k] = v

    return stats, not_found_in_oge, not_found_in_target


def map_to_student_RA(stats, cleaned_target_folder_mapping):
    res = {}
    no_student_mapping = []
    for k,v in stats.items():
        if k in cleaned_target_folder_mapping:
            res[cleaned_target_folder_mapping[k][1]] = v
        else:
            no_student_mapping.append(k)
    return res, no_student_mapping


cleaned_target_folder_mapping = _clean_target_folder_mapping(target_folder_mapping)
cleaned_oge_people_their_total_files = _clean_oge_people_their_total_files(oge_people_their_total_files)
stats,not_found_in_oge, not_found_in_target = compare_two_files(cleaned_oge_people_their_total_files, cleaned_target_folder_mapping)
student_RA, no_student_mapping = map_to_student_RA(stats, cleaned_target_folder_mapping)


#print(student_RA)
print("--------------------------------")
print(len(not_found_in_oge))
print(len(not_found_in_target))

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