import argparse
from app.github_utils import fetch_repo_zip, unzip_file
from app.file_analyzer import get_python_files, inspect_python_file
from datetime import datetime
import json
import os

def main(repo_url):
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    download_dir = "downloaded_repo"
    extract_dir = "repo_extracted"

    print(f"[+] Downloading repository from: {repo_url}")
    zip_path = fetch_repo_zip(repo_url, download_dir=download_dir, filename=f"repo_{timestamp}.zip")

    print("[+] Extracting...")
    unzip_file(zip_path, target_dir=extract_dir)

    print("[+] Collecting Python files...")
    py_files = get_python_files(extract_dir)

    print(f"[+] Found {len(py_files)} Python files. Analyzing...")
    results = []
    total_lines = 0
    long_files = []

    for file_path in py_files:
        analysis = inspect_python_file(file_path)
        total_lines += analysis["lines"]
        if analysis["lines"] > 500:
            long_files.append(file_path)
        results.append(analysis)

    summary = {
        "total_files": len(py_files),
        "total_lines": total_lines,
        "avg_lines_per_file": total_lines // len(py_files) if py_files else 0,
        "long_files": long_files
    }

    output = {
        "summary": summary,
        "file_reports": results
    }

    output_file = f"analysis_{timestamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"\n Analysis complete. Saved to: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze a GitHub repo with LLM.")
    parser.add_argument("--url", required=True, help="GitHub repo URL")
    args = parser.parse_args()
    main(args.url)
