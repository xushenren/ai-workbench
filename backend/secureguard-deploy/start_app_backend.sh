#!/bin/bash
# backend.app — 企业AI工作台 · 后端 
# 启动前先加 PATH 让 platform_storage 模块可导入
export PYTHONPATH=/opt/secureguard-deploy/backend:${PYTHONPATH}
cd /opt/secureguard-deploy
exec /opt/miniconda3/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 9002 --log-level info
