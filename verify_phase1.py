#!/usr/bin/env python3
import os
import json
import glob

def verify():
    print("==================================================")
    print("        SecondSelf Phase 1 Verification           ")
    print("==================================================")
    
    errors = 0
    warnings = 0
    
    # 1. Check directories
    print("\n[1] Checking Directory Scaffolding...")
    dirs_to_check = [
        "raw",
        "wiki",
        "wiki/Projects",
        "wiki/Areas",
        "wiki/Resources",
        "wiki/Archives",
        "templates"
    ]
    for d in dirs_to_check:
        if os.path.isdir(d):
            print(f"  [OK] Directory '{d}' exists.")
        else:
            print(f"  [FAIL] Directory '{d}' is missing.")
            errors += 1
            
    # 2. Check files in raw/
    print("\n[2] Checking Captured Items in raw/ ...")
    if not os.path.exists("raw"):
        print("  [FAIL] Cannot check raw/ because directory does not exist.")
        return
        
    json_files = glob.glob("raw/*.json")
    json_count = len(json_files)
    print(f"  Found {json_count} metadata JSON files in raw/ folder.")
    
    if json_count >= 10:
        print(f"  [OK] Found 10+ captured items ({json_count} total).")
    else:
        print(f"  [FAIL] Less than 10 items captured ({json_count} total). Needs at least 10.")
        errors += 1
        
    # 3. Check metadata files validity
    print("\n[3] Validating Metadata Entries...")
    valid_captures = 0
    types_found = set()
    
    for j_path in json_files:
        try:
            with open(j_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            has_id = "id" in data and bool(data["id"])
            has_timestamp = "timestamp" in data and bool(data["timestamp"])
            has_type = "type" in data and data["type"] in ["note", "link", "file"]
            has_source = "source" in data
            has_raw_file = "raw_file_path" in data and os.path.exists(data["raw_file_path"])
            
            if has_id and has_timestamp and has_type and has_source and has_raw_file:
                valid_captures += 1
                types_found.add(data["type"])
            else:
                print(f"  [FAIL] Malformed metadata file: {j_path}")
                if not has_raw_file:
                    print(f"    - Target raw file path is missing or does not exist: {data.get('raw_file_path')}")
                errors += 1
        except Exception as e:
            print(f"  [FAIL] Failed to parse metadata file {j_path}: {e}")
            errors += 1
            
    print(f"  Parsed {valid_captures} / {json_count} valid metadata configurations.")
    
    # 4. Check capabilities
    print("\n[4] Checking Ingested Types...")
    print(f"  Types detected in raw captures: {list(types_found)}")
    required_types = {"note", "link", "file"}
    missing_types = required_types - types_found
    if not missing_types:
        print("  [OK] Captured at least one note, one link, and one file successfully.")
    else:
        print(f"  [WARN] Missing captured types: {list(missing_types)}")
        warnings += 1
        
    print("\n==================================================")
    print(f" Verification Complete: {errors} Errors, {warnings} Warnings")
    print("==================================================")
    if errors == 0:
        print(" [SUCCESS] Phase 1 - Ingestion Pipeline Verified Successfully! ")
    else:
        print(" [FAIL] Phase 1 - Verification Failed. Please fix the errors listed above. ")
    print("==================================================")

if __name__ == "__main__":
    verify()
