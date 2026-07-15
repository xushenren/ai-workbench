#!/bin/bash
# SecureGuard backend restart with Docker sandbox
export SANDBOX_BACKEND=docker
export SANDBOX_IMAGE=python:3.12-slim
cd /root/.openclaw/workspace/secureguard-deploy
exec python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 9000
