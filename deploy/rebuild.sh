#!/bin/bash
# VPS 弱网离线构建：cache mount（已预热）+ find-links（本地轮子）+ UV_OFFLINE=1
# 注意：勿在脚本内 pkill -f rebuild（会匹配自身命令行）
cd ~/wws-adviser/deploy
for i in $(seq 1 10); do
  env WWS_TAG=cb6e575 PYPI_INDEX= UV_FIND_LINKS=http://172.17.0.1:8001 UV_OFFLINE=1 \
    docker compose build > /tmp/build-cb6e575.log 2>&1 && { echo OK > /tmp/build-status; exit 0; }
  pkill -9 -f "docker[ ]compose build" 2>/dev/null
  sleep 10
done
echo FAIL > /tmp/build-status
