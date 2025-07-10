from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from app.github_utils import fetch_repo_zip, unzip_file
from app.file_analyzer import get_python_files, inspect_python_file
import os
from datetime import datetime

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Welcome to the Codebase Analyzer API!"}

@app.get("/analyze")
def analyze_repo(url: str = Query(..., description="GitHub repo URL")):
    try:
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        zip_path = fetch_repo_zip(url, download_dir="downloaded_repo", filename=f"repo_{timestamp}.zip")
        extract_dir = f"repo_extracted_{timestamp}"
        os.makedirs(extract_dir, exist_ok=True)

        unzip_file(zip_path, target_dir=extract_dir)
        py_files = get_python_files(extract_dir)

        file_summaries = []
        total_lines = 0
        long_functions = []

        for file_path in py_files:
            analysis = inspect_python_file(file_path)
            total_lines += analysis["lines"]
            if analysis["lines"] > 500:
                long_functions.append(file_path)
            file_summaries.append(analysis)

        summary = {
            "total_lines": total_lines,
            "average_lines_per_file": total_lines // len(py_files) if py_files else 0,
            "long_functions": long_functions
        }

        return {"summary": summary, "files": file_summaries}

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)





