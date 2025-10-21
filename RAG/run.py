#!/usr/bin/env python3

import sys
from pathlib import Path

project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

if __name__ == "__main__":
    from rag.main import main
    import asyncio
    asyncio.run(main())
