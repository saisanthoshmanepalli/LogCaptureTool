import os
import sys
import zipfile
import hashlib
import json

DIST_DIR = "dist"
RELEASE_DIR = "release"

def sha256sum(filename):
    h = hashlib.sha256()
    with open(filename, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def make_zip(version):
    os.makedirs(RELEASE_DIR, exist_ok=True)
    zip_name = f"LogCaptureTool-{version}.zip"
    zip_path = os.path.join(RELEASE_DIR, zip_name)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(DIST_DIR):
            for file in files:
                filepath = os.path.join(root, file)
                arcname = os.path.relpath(filepath, DIST_DIR)
                zipf.write(filepath, arcname)

    return zip_path

def update_manifest(version, zip_path):
    sha256 = sha256sum(zip_path)
    manifest = {
        "version": version,
        "notes": "Bug fixes and improvements",
        "url": f"https://raw.githubusercontent.com/saisanthoshmanepalli/LogCaptureTool/main/release/{os.path.basename(zip_path)}",
        "sha256": sha256,
    }
    with open(os.path.join(RELEASE_DIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

def main():
    if len(sys.argv) < 2:
        print("Usage: python publish_update.py <version>")
        sys.exit(1)

    version = sys.argv[1]
    zip_path = make_zip(version)
    update_manifest(version, zip_path)
    print(f"Published {zip_path} and updated manifest.json")

if __name__ == "__main__":
    main()
