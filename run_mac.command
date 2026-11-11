#!/bin/bash
cd "$(dirname "$0")"
H=$(python3 -c "import hashlib;print(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())")
if [ "$(cat .installed 2>/dev/null)" != "$H" ]; then
  echo "Installing packages (only after an update)..."
  python3 -m pip install -q -r requirements.txt || { read -p "Install failed. Press Enter."; exit 1; }
  echo "$H" > .installed
fi
python3 launch.py
