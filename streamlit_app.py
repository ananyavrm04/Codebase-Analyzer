# streamlit_app.py
import streamlit as st
import subprocess
import tempfile
import os
import glob
import json
import time
from pathlib import Path

st.set_page_config(page_title="Codebase Analyzer — Demo", layout="wide")

st.title("Codebase Analyzer — Recruiter demo")
st.markdown(
    "Paste a GitHub repo URL or upload a zipped repository. This UI will run your existing analysis (run_analysis.py / main.py) and present recruiter-focused results."
)

col1, col2 = st.columns([3,1])

with col1:
    git_url = st.text_input("GitHub repo URL (https://github.com/owner/repo)")
    uploaded = st.file_uploader("Or upload a zipped repo (.zip)", type=["zip"])

with col2:
    fast_mode = st.checkbox("Fast mode (use existing extracted repos if available)", value=True)
    run_btn = st.button("Run Analysis")

# helper
def find_latest_analysis_json(tmpdir=None):
    # look for analysis_*.json in the working dir or tmpdir
    candidates = []
    search_roots = [os.getcwd()]
    if tmpdir:
        search_roots.append(str(tmpdir))
    for root in search_roots:
        candidates += glob.glob(os.path.join(root, "analysis_*.json"))
    if not candidates:
        # try repo_extracted files
        candidates += glob.glob("repo_extracted_*/*/analysis_*.json")
    if not candidates:
        return None
    # pick the newest file
    candidates = sorted(candidates, key=os.path.getmtime, reverse=True)
    return candidates[0]

def run_command(cmd, cwd=None, timeout=300):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        return -1, "", f"Timeout: {e}"

if run_btn:
    st.info("Starting analysis. This will run your existing script (`run_analysis.py` or `main.py`) — may take 10–120s depending on repo size.")
    tmpdir = tempfile.mkdtemp(prefix="code-analyzer-")
    analysis_path = None

    try:
        if uploaded is not None:
            # save zip
            zip_path = os.path.join(tmpdir, uploaded.name)
            with open(zip_path, "wb") as f:
                f.write(uploaded.getbuffer())
            st.write("Saved uploaded zip to:", zip_path)
            # try to run your existing run_analysis.py with zip option
            # Assumes your script can accept a zip path via CLI like: python run_analysis.py --zip path
            cmd = ["python", "run_analysis.py", "--zip", zip_path]
            st.write("Running command:", " ".join(cmd))
            code, out, err = run_command(cmd, cwd=os.getcwd(), timeout=600)
        elif git_url:
            # run with git_url argument
            cmd = ["python", "run_analysis.py", "--git_url", git_url]
            st.write("Running command:", " ".join(cmd))
            code, out, err = run_command(cmd, cwd=os.getcwd(), timeout=600)
        else:
            st.error("Please provide a GitHub URL or upload a zip.")
            st.stop()

        if code != 0:
            st.error("Analysis script returned non-zero exit.")
            st.text("STDOUT:\n" + out)
            st.text("STDERR:\n" + err)
        else:
            st.success("Analysis finished. Searching for output JSON ...")
            # find the latest analysis file
            time.sleep(1)
            analysis_path = find_latest_analysis_json(tmpdir)
            if not analysis_path:
                st.error("Could not find analysis_*.json output file. Check run_analysis.py output.")
                st.text("STDOUT:\n" + out)
                st.text("STDERR:\n" + err)
            else:
                st.write("Found analysis file:", analysis_path)
                with open(analysis_path, "r", encoding="utf-8") as f:
                    j = json.load(f)
                st.subheader("Static Analysis (raw JSON)")
                st.json(j)

                # Example: render a recruiter-friendly summary if keys exist
                st.subheader("Recruiter Summary")
                summary_lines = []
                # heuristics
                py_files = j.get("python_files", None) or j.get("num_python_files", None)
                notebooks = j.get("notebooks", None)
                has_readme = j.get("has_readme", None)
                has_docker = j.get("has_dockerfile", None)
                has_requirements = j.get("has_requirements", None)

                if py_files is not None:
                    summary_lines.append(f"• Python files: {py_files}")
                if notebooks is not None:
                    summary_lines.append(f"• Notebooks: {notebooks}")
                if has_readme:
                    summary_lines.append("• README present")
                else:
                    summary_lines.append("• README missing — add a recruiter-focused README (1-paragraph + demo + run steps).")
                if has_requirements:
                    summary_lines.append("• requirements.txt present")
                else:
                    summary_lines.append("• requirements.txt missing — add it for reproducibility.")
                if has_docker:
                    summary_lines.append("• Dockerfile present")
                else:
                    summary_lines.append("• Dockerfile missing — optional but helpful for deployment.")

                for line in summary_lines:
                    st.write(line)

                # show top files if present
                top_files = j.get("top_files", None) or j.get("files_of_interest", None)
                if top_files:
                    st.subheader("Files of Interest")
                    st.write(top_files)
                # provide download
                st.download_button("Download analysis JSON", json.dumps(j, indent=2), file_name=Path(analysis_path).name)

    finally:
        # optional cleanup - keep for debugging if you want
        pass
