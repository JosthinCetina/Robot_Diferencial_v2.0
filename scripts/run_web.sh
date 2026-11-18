#!/usr/bin/env bash
set -euo pipefail
cd /ros2_ws/web
npm ci
npm run dev -- --host 0.0.0.0
