"""Development entrypoint: uvicorn app.main:app --reload"""

import sys
from pathlib import Path
import uvicorn

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)