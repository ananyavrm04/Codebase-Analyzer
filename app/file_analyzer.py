import os
import ast
from typing import List, Dict
from app.llm_client import summarize_code

def get_python_files(root_dir: str) -> List[str]:
    files = []
    for path, _, filenames in os.walk(root_dir):
        for name in filenames:
            if name.endswith(".py"):
                files.append(os.path.join(path, name))
    return files

def inspect_python_file(path: str) -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception as error:
        return {"file": path, "error": str(error)}

    func_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    class_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]

    llm_result = summarize_code(source)

    return {
        "file": path,
        "lines": len(source.splitlines()),
        "functions": func_names,
        "classes": class_names,
        "summary": llm_result
    }
