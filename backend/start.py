import os
import sys

# Move into the backend directory so all relative imports work
backend_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

port = int(os.environ.get("PORT", 8000))
print(f"Starting on port {port}", flush=True)

import uvicorn
import main as app_module

uvicorn.run(app_module.app, host="0.0.0.0", port=port)
