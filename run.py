"""
Launcher script for NTRO Thermal Anomaly & Fire Intelligence Platform
Starts the FastAPI backend and automatically opens the scientific GIS console in your browser.
"""

import os
import sys
import webbrowser
import uvicorn
from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    # Ensure backend is in python path
    project_root = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(project_root, "backend"))

    print("==========================================================================")
    print(" NTRO | THERMAL ANOMALY & INDUSTRIAL FIRE INTELLIGENCE PLATFORM (SIH26162) ")
    print("==========================================================================")
    print("Starting server at: http://127.0.0.1:8000")
    print("Interactive API docs: http://127.0.0.1:8000/docs")
    print("Opening browser...")

    # Open browser automatically after slight delay
    webbrowser.open("http://127.0.0.1:8000")

    # Run Uvicorn server
    from backend.app.main import app
    uvicorn.run(app, host="127.0.0.1", port=8000)
