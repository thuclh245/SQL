"""Launcher for T2S Copilot Web Application."""

from __future__ import annotations

import uvicorn
from backend.main import app

if __name__ == "__main__":
    print("\n⚡ T2S Copilot Web Server is running at: http://localhost:8080\n")
    uvicorn.run(app, host="0.0.0.0", port=8080)
