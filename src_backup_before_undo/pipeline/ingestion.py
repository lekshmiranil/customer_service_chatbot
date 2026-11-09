import os
import shutil
import hashlib
import json
from src.pipeline.security import mask_sensitive_data, detect_prompt_injection
from pathlib import Path
from datetime import datetime

# Define pipeline directories
RAW_DATA_DIR = Path("dataset/raw")
STAGING_DIR = Path("dataset/staging")
QUARANTINE_DIR = Path("dataset/quarantine")
MANIFEST_PATH = Path("dataset/manifest.json")
VERSIONS_DIR = Path("faiss_versions")
STAGING_BACKUP_DIR = Path("dataset/.staging_backup")
SUPPORTED_EXTENSIONS = {".csv", ".txt", ".md"}

# Ensure directories exist
for d in [RAW_DATA_DIR, STAGING_DIR, QUARANTINE_DIR, VERSIONS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash to detect file contents and duplicates."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def load_manifest() -> dict:
    """Load the document version manifest tracking active hashes."""
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, "r") as f:
            return json.load(f)
    return {"version": 0, "documents": {}}


def save_manifest(manifest: dict):
    """Save the updated manifest state."""
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=4)

def backup_staging():
    """Saves a copy of the staging folder so a failed attempt can be undone."""
    if STAGING_BACKUP_DIR.exists():
        shutil.rmtree(STAGING_BACKUP_DIR)
    shutil.copytree(STAGING_DIR, STAGING_BACKUP_DIR)


def restore_staging():
    """Puts the staging folder back to how it was before the attempt."""
    if STAGING_BACKUP_DIR.exists():
        shutil.rmtree(STAGING_DIR)
        shutil.copytree(STAGING_BACKUP_DIR, STAGING_DIR)


def process_incoming_documents() -> list:
    """
    Scans the raw directory, skips duplicates, quarantines invalid or
    suspicious files (empty, or containing prompt-injection text), masks
    sensitive data, and stages new or modified files.
    """
    manifest = load_manifest()
    documents_registry = manifest.get("documents", {})
    staged_files = []

    # Hashes of all known content, so duplicates are caught under any filename
    known_hashes = {metadata["hash"] for metadata in documents_registry.values()}

    if not RAW_DATA_DIR.exists():
        print("Raw data directory missing.")
        return staged_files

    for file_path in RAW_DATA_DIR.glob("*.*"):
        try:
            if file_path.stat().st_size == 0:
                raise ValueError("File is empty.")

            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                raise ValueError(f"Unsupported file type '{file_path.suffix}'.")


            file_hash = compute_file_hash(file_path)

            # Same filename, same content -> unchanged
            existing = documents_registry.get(file_path.name)
            if existing and existing["hash"] == file_hash:
                print(f"Skipping duplicate/unchanged file: {file_path.name}")
                continue

            # Same content under a different filename -> duplicate
            if file_hash in known_hashes:
                print(f"Skipping duplicate content (different filename): {file_path.name}")
                continue

            # Decode with surrogateescape so any original encoding survives
            # the round trip byte for byte.
            raw_bytes = file_path.read_bytes()
            text = raw_bytes.decode("utf-8", errors="surrogateescape")

            # Prompt-injection text in a document would poison the knowledge base
            if detect_prompt_injection(text):
                raise ValueError("Possible prompt injection detected in document content.")

            # Mask sensitive data before the document reaches the index
            masked_text = mask_sensitive_data(text)
            if masked_text != text:
                print(f"Masked sensitive data in {file_path.name}")

            target_path = STAGING_DIR / file_path.name
            target_path.write_bytes(masked_text.encode("utf-8", errors="surrogateescape"))

            documents_registry[file_path.name] = {
                "hash": file_hash,
                "status": "staged",
                "updated_at": datetime.utcnow().isoformat()
            }
            known_hashes.add(file_hash)
            staged_files.append(target_path)
            print(f"Staged new/modified file: {file_path.name}")

        except Exception as e:
            quarantine_path = QUARANTINE_DIR / file_path.name
            shutil.move(file_path, quarantine_path)
            print(f"Quarantined invalid file '{file_path.name}' due to error: {e}")

    manifest["documents"] = documents_registry
    save_manifest(manifest)
    return staged_files

def create_version_snapshot(current_index_path: str) -> str:
    """Creates an isolated version snapshot of the vector index for rollbacks."""
    manifest = load_manifest()
    new_version_num = manifest.get("version", 0) + 1
    version_folder = VERSIONS_DIR / f"v{new_version_num}"

    if os.path.exists(current_index_path):
        shutil.copytree(current_index_path, version_folder, dirs_exist_ok=True)
        manifest["version"] = new_version_num
        save_manifest(manifest)
        print(f"Created rollback vector database snapshot: {version_folder}")
        return str(version_folder)
    
    return None


def rollback_version(target_version: int, active_index_path: str) -> bool:
    """Rolls back the active vector database to a previous snapshot version."""
    target_folder = VERSIONS_DIR / f"v{target_version}"
    if target_folder.exists():
        if os.path.exists(active_index_path):
            shutil.rmtree(active_index_path)
        shutil.copytree(target_folder, active_index_path)
        print(f"Successfully rolled back vector database to version {target_version}")
        return True
    print(f"Rollback failed: Version v{target_version} does not exist.")
    return False