#!/usr/bin/env python3
"""
Check the old annotations file to show the bug existed before the fix.
"""

import json

def main():
    print("=" * 70)
    print("CHECKING OLD ANNOTATIONS FILE FOR BUG")
    print("=" * 70)
    print()

    with open('annotations/target_als_test_file_templates.json', 'r') as f:
        data = json.load(f)

    # Find problematic files
    pdf_with_wrong_format = []
    txt_with_wrong_format = []

    for folder_id, files in data.items():
        for filename, annots in files.items():
            file_format = annots.get('fileFormat', 'N/A')

            # Check PDF files with wrong format
            if filename.endswith('.pdf') and file_format != 'pdf':
                pdf_with_wrong_format.append({
                    'filename': filename,
                    'fileFormat': file_format,
                    'folder': folder_id
                })

            # Check TXT files with wrong format
            if ('.txt' in filename or '.txt.gz' in filename) and file_format not in ['txt', 'N/A']:
                txt_with_wrong_format.append({
                    'filename': filename,
                    'fileFormat': file_format,
                    'folder': folder_id
                })

    print(f"PDF files with WRONG fileFormat: {len(pdf_with_wrong_format)}")
    print(f"TXT files with WRONG fileFormat: {len(txt_with_wrong_format)}")
    print()

    if pdf_with_wrong_format:
        print("Sample PDF files with wrong format (showing first 5):")
        for item in pdf_with_wrong_format[:5]:
            print(f"  ❌ {item['filename']}")
            print(f"     fileFormat: {item['fileFormat']} (should be 'pdf')")
            print()

    if txt_with_wrong_format:
        print("Sample TXT files with wrong format (showing first 5):")
        for item in txt_with_wrong_format[:5]:
            print(f"  ❌ {item['filename']}")
            print(f"     fileFormat: {item['fileFormat']} (should be 'txt')")
            print()

    # Check the specific file mentioned in the bug report
    print("Checking the specific file from bug report:")
    found = False
    for folder_id, files in data.items():
        for filename, annots in files.items():
            if 'NEUBJ004MUV' in filename and 'gc_bias.pdf' in filename:
                print(f"  File: {filename}")
                print(f"  fileFormat: {annots.get('fileFormat', 'N/A')} (should be 'pdf')")
                print(f"  Folder: {folder_id}")
                found = True
                break
        if found:
            break

    print()
    print("=" * 70)
    print(f"TOTAL FILES WITH WRONG FORMAT: {len(pdf_with_wrong_format) + len(txt_with_wrong_format)}")
    print("=" * 70)

if __name__ == '__main__':
    main()
