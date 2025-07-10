# 🧠 Codebase Analyzer

An intelligent LLM-powered tool that downloads and analyzes GitHub repositories, automatically summarizing Python files using Together AI's models. Built with FastAPI and CLI support, it's designed for backend engineers and AI enthusiasts who want to explore and understand large codebases quickly.

## 🚀 Features

- 📥 Downloads GitHub repositories from URL input  
- 📂 Extracts and parses all `.py` files  
- 🧠 Summarizes code using Together AI (Llama/Mistral models)  
- 📊 Calculates total/average lines and detects large files  
- 🔗 Accessible via both **CLI** and **FastAPI API**  
- ✅ Clean modular structure and secure API key usage  

## 📁 Project Structure
codebase_analyzer/
│
├── app/
│ ├── github_utils.py # Repo downloading & extraction
│ ├── file_analyzer.py # Python file parsing
│ ├── llm_client.py # LLM summarization
│
├── main.py # FastAPI backend (optional)
├── run_analysis.py # CLI version (primary usage)
├── test_llm.py # Quick LLM summarization test
├── requirements.txt # Clean dependency list
└── README.md # You're here

## ⚙️ Installation

```bash
git clone https://github.com/your-username/codebase-analyzer.git
cd codebase-analyzer

# Setup virtual environment
python -m venv venv
venv\Scripts\activate     # For Windows
# source venv/bin/activate  # For macOS/Linux

# Install dependencies
pip install -r requirements.txt

