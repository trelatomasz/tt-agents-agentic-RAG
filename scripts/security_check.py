#!/usr/bin/env python3
"""Security & Identity Leak Scanner.

Scans the repository to ensure no credentials, tokens, real GCP project IDs,
or personal email addresses are ever committed.
"""

import os
import re
import sys
import subprocess

FORBIDDEN_PATTERNS = [
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "Private Key"),
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token"),
    (r"gho_[a-zA-Z0-9]{36}", "GitHub OAuth Token"),
    (r"AIza[0-9A-Za-z-_]{35}", "Google API Key"),
    (r"ya29\.[0-9A-Za-z-_]+", "Google OAuth Access Token"),
    (r"(?i)(password|secret)\s*[:=]\s*[\"'][^\"']{8,}[\"']", "Hardcoded Secret"),
    (r"[a-zA-Z0-9._%+-]+@(?!example\.com|users\.noreply\.github\.com|schema\.org)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "Real Email Address"),
]

# Forbidden project ID patterns
FORBIDDEN_KEYWORDS = [
    ("505805", "Private GCP Project ID"),
    ("pikson", "Personal Identity / Username"),
]

IGNORE_DIRS = {".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__", ".idea", ".vscode"}


def get_tracked_files():
    try:
        out = subprocess.check_output(["git", "ls-files"], text=True)
        return set(out.splitlines())
    except Exception:
        return None


def main():
    tracked = get_tracked_files()
    violations = []

    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for file in files:
            filepath = os.path.normpath(os.path.join(root, file))
            
            # If git is available, only scan tracked files + staged files
            if tracked is not None and filepath not in tracked:
                continue

            # Fail immediately if sensitive files are tracked
            if file in {".env", "terraform.tfvars"} or file.endswith((".tfstate", ".key", ".pem")):
                violations.append((filepath, 0, "Gitignored sensitive file is tracked in git!"))
                continue

            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        # Check patterns
                        for pattern, desc in FORBIDDEN_PATTERNS:
                            if re.search(pattern, line):
                                if "your-email@example.com" in line or "your-gcp-project-id" in line:
                                    continue
                                violations.append((filepath, line_num, f"{desc}: {line.strip()[:80]}"))

                        # Check keywords
                        for kw, desc in FORBIDDEN_KEYWORDS:
                            if kw.lower() in line.lower():
                                violations.append((filepath, line_num, f"{desc}: {line.strip()[:80]}"))

            except Exception as e:
                print(f"Warning: Could not read {filepath}: {e}", file=sys.stderr)

    if violations:
        print(f"[SECURITY ALERT] Found {len(violations)} security violation(s):", file=sys.stderr)
        for filepath, line_num, msg in violations:
            print(f"  {filepath}:{line_num} -> {msg}", file=sys.stderr)
        sys.exit(1)
    else:
        print("[SUCCESS] Security scan passed: Zero identity or credential leaks detected.")
        sys.exit(0)


if __name__ == "__main__":
    main()
