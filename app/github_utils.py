import os
import zipfile
import requests


def fetch_repo_zip(repo_url: str, download_dir: str = "downloaded_repo", filename: str = "repo.zip") -> str:
    if not repo_url.endswith(".git"):
        repo_url += ".git"

    try:
        repo_path = repo_url.split("github.com/")[1].replace(".git", "")
        zip_url = f"https://github.com/{repo_path}/archive/refs/heads/main.zip"

        response = requests.get(zip_url)
        if response.status_code == 200:
            os.makedirs(download_dir, exist_ok=True)
            zip_file = os.path.join(download_dir, filename)
            with open(zip_file, "wb") as f:
                f.write(response.content)
            print(f" Repo downloaded to: {zip_file}")
            return zip_file
        else:
            raise Exception(f" Failed to fetch repo. HTTP status: {response.status_code}")
    
    except Exception as e:
        print(f" Error during repo fetch: {e}")
        return None  # So that downstream logic can catch the failure


def unzip_file(zip_path: str, target_dir: str):
    if not zip_path:
        raise ValueError("zip_path is None. Cannot unzip.")
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(target_dir)
        print(f" Extraction complete to: {target_dir}")
    except Exception as e:
        print(f" Failed to unzip: {e}")
        raise

