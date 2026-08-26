# -*- coding: utf-8 -*-
"""
Institutional Breakout Intelligence Terminal — Main Entrypoint

Reroutes execution to frontend/terminal.py for Streamlit Community Cloud and local run.
"""
import os
import sys
import runpy

# Ensure root directory and frontend directory are present in sys.path
root_dir = os.path.dirname(os.path.abspath(__file__))
frontend_dir = os.path.join(root_dir, "frontend")

if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
if frontend_dir not in sys.path:
    sys.path.insert(0, frontend_dir)

# Run the 7-Layer Breakout Intelligence Terminal
target_script = os.path.join(frontend_dir, "terminal.py")
runpy.run_path(target_script, run_name="__main__")
