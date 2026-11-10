#!/bin/bash
cd "$(dirname "$0")"
if true; then
  python3 -m pip install -q -r requirements.txt || { read -p "Install failed. Press Enter."; exit 1; }
fi
python3 launch.py
