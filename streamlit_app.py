import streamlit as st
import subprocess
import tempfile
import os
import glob
import json
import time
from pathlib import Path

st.set_page_config(page_title="Codebase Analyzer — Demo", layout="wide")

st.title("Codebase Analyzer — Recruiter Demo")
st.markdown(
    "Analyze any GitHub repository and generate insights into its Python codebase. "
    "This UI uses your existing `run_analysis.py` script and displays the generated JSON output."
)

st.divider()

# -------------------------
# INPUT SECTION
# -------------------------
git_url = st.text_input(
    "Enter GitHub Repository URL",
    placeholder="https://github.com/user/repo",
)

run_btn = st.button("Run Analysis")

# -------------------------
# Helper: find latest analysis JSON
# -------------------------
def find_latest_json():
    json_files = glob.glob("analysis_*.json")
    if not json_files:
        return None
    return max(json_files, key=os.path.getmtime)

# -------------------------
# RUN ANALYSIS
# -------------------------
if run_btn:
    if not git_url.strip():
        st.error("Please enter a GitHub repository URL.")
        st.stop()

    st.info("Running analysis... This may take 10–60 seconds depending on repo size.")
    
    cmd = ["python", "run_analysis.py", "--url", git_url]

    with st.spinner("Analyzing repository..."):
        try:
            # Run script
            process = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300
            )
        except subprocess.TimeoutExpired:
            st.error("❌ Script timed out. Try a smaller repository.")
            st.stop()

        # Display script output (stdout/stderr)
        with st.expander("🔍 Script Output (stdout)"):
            st.text(process.stdout)

        with st.expander("⚠️ Script Errors (stderr)"):
            st.text(process.stderr)

        # Check return code
        if process.returncode != 0:
            st.error("❌ Script failed. Check stderr above.")
            st.stop()

        # Find latest analysis JSON
        json_path = find_latest_json()
        if not json_path:
            st.error("❌ No analysis_*.json file generated. Script may not have run correctly.")
            st.stop()

        st.success(f"Analysis completed! Loaded results from `{json_path}`")

        # Load JSON
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # -------------------------
        # DISPLAY JSON RESULTS
        # -------------------------
        st.header("📌 Summary")
        st.json(data.get("summary", {}))

        st.header("📁 File Reports")
        st.write("Showing Python file analysis results:")
        st.json(data.get("file_reports", []))

        # Optional: Download JSON
        st.download_button(
            label="📥 Download Analysis JSON",
            data=json.dumps(data, indent=2),
            file_name=os.path.basename(json_path),
            mime="application/json",
        )
