"""Render startup script — resolves $PORT and sets correct working directory."""
import os
import sys
import subprocess

os.chdir(os.path.dirname(os.path.abspath(__file__)))
port = os.environ.get("PORT", "8000")
result = subprocess.run(
    [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", port]
)
sys.exit(result.returncode)
