#!/bin/bash
echo "=== Installing frontend ==="
cd frontend_src && npm install
echo "=== Installing backend ==="
cd ../backend/secureguard-deploy && pip install -r requirements.txt
echo "=== Done ==="
