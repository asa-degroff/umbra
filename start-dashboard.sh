#!/bin/bash
cd /home/asa/umbra
exec /home/asa/umbra/.venv/bin/uvicorn dashboard.backend.main:app --host 0.0.0.0 --port 8081
