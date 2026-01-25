#!/usr/bin/env python3
"""
Target Folder Mapping Generator

Scans the RA_collection directory and creates a JSON mapping of:
- Key: Target folder name (e.g., "Donald,_L_Palmer")
- Value: [file_count, page_folder_name]

Structure: RA_collection/{person}/{page_folder}/{target_folder}/files.pdf
Example: RA_collection/Aarav Kumar/RA_Collection_Aarav_Kumar_Page_37/Donald,_L_Palmer/file.pdf
Result: {"Donald,_L_Palmer": [5, "RA_Collection_Aarav_Kumar_Page_37"]}
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict


def scan_ra_collection_for_target_folders(ra_collection_path: Path) -> Dict[str, List]:
    """Scan RA_collection and create a mapping of target folders to file counts.
    
    Structure expected:
    RA_collection/
        {person_folder}/
            {page_folder}/
                {target_folder}/
                    file1.pdf
                    file2.pdf
    
    Args:
        ra_collection_path: Path to the RA_collection directory
        
    Returns:
        Dictionary mapping target_folder_name -> [file_count, page_folder_name]
    """
    
    target_folder_mapping = {}
    
    # Check if directory exists
    if not ra_collection_path.exists():
        print(f"❌ Error: Directory not found: {ra_collection_path}")
        return {}
    
    # Iterate through person folders (top-level directories)
    for person_folder in ra_collection_path.iterdir():
        # Skip if not a directory or if it's a hidden folder
        if not person_folder.is_dir() or person_folder.name.startswith('.'):
            continue
        
        person_name = person_folder.name
        print(f"\n📂 Scanning person folder: {person_name}")
        
        # Iterate through page folders (second level)
        for page_folder in person_folder.iterdir():
            # Skip if not a directory
            if not page_folder.is_dir() or page_folder.name.startswith('.'):
                continue
            
            page_folder_name = page_folder.name
            print(f"   📄 Page folder: {page_folder_name}")
            
            # Iterate through target folders (third level - these are the keys we want)
            for target_folder in page_folder.iterdir():
                # Skip if not a directory
                if not target_folder.is_dir() or target_folder.name.startswith('.'):
                    continue
                
                target_folder_name = target_folder.name
                
                # Count PDF files in this target folder
                pdf_count = 0
                for file in target_folder.iterdir():
                    if file.is_file() and file.name.lower().endswith('.pdf'):
                        pdf_count += 1
                
                # Store in mapping: target_folder -> [file_count, page_folder]
                if target_folder_name in target_folder_mapping:
                    # If target folder already exists (same person appears in multiple pages)
                    # Add the counts
                    existing_count = target_folder_mapping[target_folder_name][0]
                    existing_page = target_folder_mapping[target_folder_name][1]
                    target_folder_mapping[target_folder_name] = [
                        existing_count + pdf_count,
                        f"{existing_page}, {page_folder_name}"
                    ]
                    print(f"      🔄 Updated: {target_folder_name} -> {pdf_count} PDFs (duplicate)")
                else:
                    target_folder_mapping[target_folder_name] = [pdf_count, page_folder_name]
                    print(f"      ✓ {target_folder_name} -> {pdf_count} PDFs")
    
    return target_folder_mapping


def save_mapping(mapping: Dict, output_path: Path):
    """Save the mapping to a JSON file.
    
    Args:
        mapping: Dictionary mapping target_folder -> [file_count, page_folder]
        output_path: Path where to save the JSON file
    """
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Mapping saved to: {output_path}")
    except Exception as e:
        print(f"\n❌ Error saving mapping: {e}")


def generate_people_all_files():
    """Generate a list of all files for each person. This is from teh automation script."""
    
    REQS_FILE_PATH = "../requested_documents.json"
    ALL_LAST_NAME_PEOPLE_PATH = "../DirectDownloads/row_individual.json"
    DIRECT_DOWNLOADS_PERSON_MAPPING_PATH = "../DirectDownloads/direct_downloads_person_mapping.json"
    
    res = {}
    cleaned_res = {}
    cleaned_all_last_name_people = {}
    final_res_last_name_only = {}

    with open(REQS_FILE_PATH, 'r') as f:
        all_reqs = json.load(f)

    with open(ALL_LAST_NAME_PEOPLE_PATH, 'r') as f:
        all_last_name_people = json.load(f)

    for k,v in all_reqs.items():
        res[k] = len(v)
    
    #now we add the number of files from the direct_downloads_person_mapping.json file
    with open(DIRECT_DOWNLOADS_PERSON_MAPPING_PATH, 'r') as f:
        direct_downloads_person_mapping = json.load(f)

    print("total Direct Downloads are: ", sum(direct_downloads_person_mapping.values()))
    print("total Requests are: ", sum(res.values()))

    for k,v in direct_downloads_person_mapping.items():
        #remove all _ from k and replace with a space
        k = k.replace('_', ' ')
        k = k.lower()
        if k not in res:
            res[k] = v
        else:
            res[k] += v

    #lets clean res
    for k,v in res.items():
        k = k.split(",")[0]
        k = k.lower()
        final_res_last_name_only[k] = final_res_last_name_only.get(k, 0) + v


    #save the results to a json file
    with open('oge_people_their_total_files.json', 'w', encoding='utf-8') as f:
        json.dump(final_res_last_name_only, f, indent=2, ensure_ascii=False)

    #total files present in the oge_people_their_total_files.json file
    total_files = sum(final_res_last_name_only.values())
    print(f"Total files present in the oge_people_their_total_files.json file: {total_files}")


def _clean_hashname(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    remove_keys = []
    for k,v in data.items():
        if "Aarav_Kumar" in v[1] or "Kumar_Aarav" in v[1]:
            remove_keys.append(k)
    
    for k in remove_keys:
        del data[k]
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def print_summary(mapping: Dict):
    """Print a summary of the mapping.
    
    Args:
        mapping: Dictionary mapping target_folder -> [file_count, page_folder]
    """
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"Total target folders found: {len(mapping)}")
    
    # Calculate total files
    total_files = sum(count for count, _ in mapping.values())
    print(f"Total PDF files across all target folders: {total_files}")
    
    # Show top 10 folders by file count
    print(f"\nTop 10 folders by file count:")
    print("-" * 100)
    sorted_folders = sorted(mapping.items(), key=lambda x: x[1][0], reverse=True)
    for i, (folder_name, (file_count, page_folder)) in enumerate(sorted_folders[:10], 1):
        print(f"  {i:2d}. {folder_name:50s} : {file_count:4d} PDFs (from {page_folder})")
    
    # Show folders with no files
    empty_folders = [(name, page) for name, (count, page) in mapping.items() if count == 0]
    if empty_folders:
        print(f"\n Folders with no PDF files: {len(empty_folders)}")
        for name, page in empty_folders[:5]:
            print(f"     - {name} (from {page})")
        if len(empty_folders) > 5:
            print(f"     ... and {len(empty_folders) - 5} more")
    
    print("=" * 100)


def main():
    """Main execution function."""
    print("=" * 100)
    print("Target Folder Mapping Generator")
    print("=" * 100)
    print()
    
    # Define paths
    script_dir = Path(__file__).parent
    ra_collection = script_dir.parent / "RA_collection"
    output_mapping = script_dir / "target_folder_mapping.json"
    
    print(f"RA Collection path: {ra_collection}")
    print(f"Output mapping: {output_mapping}")
    print()
    
    # Scan the collection for target folders
    target_mapping = scan_ra_collection_for_target_folders(ra_collection)
    
    if not target_mapping:
        print("\n No target folders found or directory doesn't exist.")
        return
    
    # Save the mapping
    save_mapping(target_mapping, output_mapping)
    
    # Print summary
    print_summary(target_mapping)
    
    # Generate people's total files (keep the existing function)
    print("\n Generating OGE people total files...")
    generate_people_all_files()

    # Clean the hashname
    print("\n Cleaning the hashname...")
    _clean_hashname("target_folder_mapping.json")


if __name__ == "__main__":
    main()