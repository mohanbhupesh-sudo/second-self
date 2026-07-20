#!/usr/bin/env python3
import os
import sys
import json
import uuid
import shutil
import argparse
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

# Default directories
RAW_DIR = "raw"

def init_raw_dir():
    """Ensure that the raw directory exists."""
    if not os.path.exists(RAW_DIR):
        os.makedirs(RAW_DIR)

def save_capture(capture_type, source, content, raw_file_suffix="txt", file_to_copy=None):
    """
    Saves a captured item to the raw directory.
    Creates a metadata JSON file and a raw content file.
    """
    init_raw_dir()
    unique_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    # Define paths
    raw_file_name = f"{unique_id}.{raw_file_suffix}"
    raw_file_path = os.path.join(RAW_DIR, raw_file_name)
    metadata_file_path = os.path.join(RAW_DIR, f"{unique_id}.json")
    
    # Save the raw content or copy the file
    if file_to_copy:
        try:
            shutil.copy2(file_to_copy, raw_file_path)
        except Exception as e:
            print(f"Error copying raw file: {e}", file=sys.stderr)
            return None
    else:
        try:
            with open(raw_file_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            print(f"Error writing content file: {e}", file=sys.stderr)
            return None
            
    # Prepare metadata
    metadata = {
        "id": unique_id,
        "timestamp": timestamp,
        "type": capture_type,
        "source": source,
        "raw_file_path": raw_file_path.replace("\\", "/"),
        "processed": False
    }
    
    # Write metadata JSON
    try:
        with open(metadata_file_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
    except Exception as e:
        print(f"Error writing metadata file: {e}", file=sys.stderr)
        return None
        
    print(f"Successfully captured {capture_type}!")
    print(f"  ID: {unique_id}")
    print(f"  Metadata: {metadata_file_path}")
    print(f"  Raw Content: {raw_file_path}")
    return unique_id

def capture_note(note_text):
    """Capture a simple text note."""
    if not note_text.strip():
        print("Error: Note cannot be empty.", file=sys.stderr)
        return None
    return save_capture("note", "Manual Capture", note_text, "txt")

def capture_link(url):
    """Scrape a URL and capture its text content."""
    print(f"Scraping URL: {url}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching URL: {e}", file=sys.stderr)
        return None
        
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Extract page title
    title = soup.title.string.strip() if soup.title else "Scraped Web Page"
    
    # Strip unnecessary tags
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
        
    # Get clean text
    text = soup.get_text(separator="\n")
    
    # Clean up empty lines
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned_content = f"Title: {title}\nURL: {url}\n\n" + "\n".join(lines)
    
    return save_capture("link", url, cleaned_content, "txt")

def capture_file(file_path):
    """Capture a local file (TXT, MD, PDF, etc.)."""
    # 1. Expand environment variables and user home folder (~)
    expanded_path = os.path.expandvars(os.path.expanduser(file_path))
    
    # 2. If path doesn't exist, search recursively in common workspace folders
    if not os.path.exists(expanded_path):
        filename = os.path.basename(file_path)
        search_dirs = [
            ".",
            "raw",
            "wiki",
            "wiki/Projects",
            "wiki/Areas",
            "wiki/Resources",
            "wiki/Archives",
            "templates"
        ]
        found = False
        for directory in search_dirs:
            candidate = os.path.join(directory, filename)
            if os.path.exists(candidate):
                expanded_path = candidate
                found = True
                break
        
        if not found:
            print(f"Error: File '{file_path}' does not exist.", file=sys.stderr)
            return None
            
    ext = os.path.splitext(expanded_path)[1].lower().strip(".")
    if not ext:
        ext = "txt"
        
    extracted_text = ""
    
    # Read/parse files depending on type
    if ext == "pdf":
        print(f"Parsing PDF file: {expanded_path}")
        try:
            reader = PdfReader(expanded_path)
            pages_text = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            extracted_text = "\n".join(pages_text)
            
            if not extracted_text.strip():
                print("Warning: PDF contains no text (it might be scanned). Storing as raw binary file.", file=sys.stderr)
        except Exception as e:
            print(f"Error reading PDF: {e}", file=sys.stderr)
            return None
    elif ext in ["txt", "md", "csv", "json", "html"]:
        print(f"Reading text file: {expanded_path}")
        try:
            with open(expanded_path, "r", encoding="utf-8", errors="replace") as f:
                extracted_text = f.read()
        except Exception as e:
            print(f"Error reading text file: {e}", file=sys.stderr)
            return None
    else:
        print(f"Unknown file type '.{ext}'. Copying raw file without parsing text content.", file=sys.stderr)
        
    # Copy the file to raw/
    unique_id = save_capture("file", expanded_path, content=None, raw_file_suffix=ext, file_to_copy=expanded_path)
    
    if unique_id and extracted_text.strip():
        extracted_txt_name = f"{unique_id}_extracted.txt"
        extracted_txt_path = os.path.join(RAW_DIR, extracted_txt_name)
        try:
            with open(extracted_txt_path, "w", encoding="utf-8") as f:
                f.write(extracted_text)
            
            # Update metadata JSON
            metadata_file_path = os.path.join(RAW_DIR, f"{unique_id}.json")
            with open(metadata_file_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            
            metadata["extracted_text_path"] = extracted_txt_path.replace("\\", "/")
            
            with open(metadata_file_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
                
        except Exception as e:
            print(f"Error writing extracted text: {e}", file=sys.stderr)
            
    return unique_id

def main():
    parser = argparse.ArgumentParser(description="Capture pipeline for SecondSelf Brain")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--note", type=str, help="Capture a raw text note")
    group.add_argument("--link", type=str, help="Scrape and capture a web page link")
    group.add_argument("--file", type=str, help="Capture a local file (TXT, MD, PDF, etc.)")
    
    args = parser.parse_args()
    
    if args.note:
        capture_note(args.note)
    elif args.link:
        capture_link(args.link)
    elif args.file:
        import glob
        pattern = os.path.expandvars(os.path.expanduser(args.file))
        
        # Check if the pattern contains wildcards
        if any(char in pattern for char in ['*', '?']):
            matched_files = glob.glob(pattern)
            if not matched_files:
                # Fallback search inside workspace subdirectories if no match in current dir
                filename_pattern = os.path.basename(pattern)
                search_dirs = [
                    ".",
                    "raw",
                    "wiki",
                    "wiki/Projects",
                    "wiki/Areas",
                    "wiki/Resources",
                    "wiki/Archives",
                    "templates"
                ]
                matched_files = []
                for directory in search_dirs:
                    candidate_pattern = os.path.join(directory, filename_pattern)
                    matches = glob.glob(candidate_pattern)
                    if matches:
                        matched_files.extend(matches)
            
            if not matched_files:
                print(f"Error: No files matched pattern '{args.file}'.", file=sys.stderr)
            else:
                print(f"Matched {len(matched_files)} files: {matched_files}")
                for file_path in matched_files:
                    if os.path.isfile(file_path):
                        capture_file(file_path)
        else:
            capture_file(args.file)

if __name__ == "__main__":
    main()
