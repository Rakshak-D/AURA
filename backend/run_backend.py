import sys
from pathlib import Path

import uvicorn

from backend.app.config import config

sys.path.append(str(Path(__file__).parent.parent))

if __name__ == "__main__":
    uvicorn.run(
        "backend.app.main:app",
        host=config.host,
        port=config.port,
        reload=config.reload,
        log_level=config.log_level.lower(),
    )
