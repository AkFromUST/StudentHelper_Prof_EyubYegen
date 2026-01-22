"""
Script to count PDF files in the RA_collection directory
"""

import os
from pathlib import Path
import json
# Define the RA_collection directory path
RA_COLLECTION_DIR = '../RA_collection'
DIRECT_DOWNLOADS_DIR = '../DirectDownloads/direct_downloads'
REQS_FILE_PATH = '../requested_documents.json'

def count_reqs_file(JSON_PATH):
    with open(JSON_PATH, 'r') as f:
        reqs = json.load(f)
    
    total = 0
    for k,v in reqs.items():
        total += len(v)
    return total

def count_pdf_files(directory):
    """
    Count all PDF files in a directory and its subdirectories
    
    Args:
        directory: Path to the directory to search
        
    Returns:
        tuple: (total_count, breakdown_by_student)
    """
    pdf_count = 0
    student_breakdown = {}
    
    directory_path = Path(directory)
    
    if not directory_path.exists():
        print(f"Error: Directory {directory} does not exist")
        return 0, {}
    
    # Get all immediate subdirectories (student folders)
    student_folders = [f for f in directory_path.iterdir() if f.is_dir()]
    
    for student_folder in sorted(student_folders):
        student_name = student_folder.name
        # Count PDFs recursively in this student's folder
        pdf_files = list(student_folder.rglob('*.pdf'))
        count = len(pdf_files)
        student_breakdown[student_name] = count
        pdf_count += count
    
    return pdf_count, student_breakdown


def main():
    print("=" * 70)
    print("PDF File Counter for RA_collection Directory")
    print("=" * 70)
    print()
    
    total_pdfs, breakdown = count_pdf_files(RA_COLLECTION_DIR)
    
    print(f"Total PDF files found: {total_pdfs:,}")
    print()
    print("-" * 70)
    print("Breakdown by student:")
    print("-" * 70)
    
    for student, count in breakdown.items():
        print(f"{student:<40} {count:>8,} PDFs")
    
    print("-" * 70)
    print(f"{'Total':<40} {total_pdfs:>8,} PDFs")
    print("=" * 70)
    
    a,b = count_pdf_files(DIRECT_DOWNLOADS_DIR)
    total_reqs = count_reqs_file(REQS_FILE_PATH)

    # Save results to a JSON file
    import json
    output_file = 'pdf_count_results.json'
    results = {
        'total_pdfs': total_pdfs,
        'breakdown_by_student': breakdown,
        'total_reqs': total_reqs,
        'total_direct_downloads': a
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\nResults saved to: {output_file}")

if __name__ == "__main__":
    main()
