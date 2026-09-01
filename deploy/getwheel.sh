#!/bin/bash
# 断点续传拉取锁定的 polars-runtime-32 轮子并本地起 HTTP 供给（VPS 弱网构建绕行）
set -u
URL="https://files.pythonhosted.org/packages/62/60/64deacb3abc70c52e2d88a808a052d1621c86a48fe9194f2c065579ab1cd/polars_runtime_32-1.43.2-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
FNAME="polars_runtime_32-1.43.2-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
EXPECT_SHA="6d5a7ae004a2723ebf4427f6d6a639f30f86af4cf077"
mkdir -p "$HOME/wheels"
for i in $(seq 1 80); do
  curl -sS -L -C - --max-time 240 -o "$HOME/wheels/$FNAME" "$URL" && break
  sleep 3
done
SIZE=$(stat -c %s "$HOME/wheels/$FNAME" 2>/dev/null || echo 0)
SHA=$(sha256sum "$HOME/wheels/$FNAME" 2>/dev/null | cut -c1-40)
echo "size=$SIZE sha_prefix=$SHA"
case "$SHA" in "$EXPECT_SHA"*) echo HASH_OK ;; *) echo HASH_MISMATCH; exit 1 ;; esac
pkill -f "http.server 8001" 2>/dev/null
nohup python3 -m http.server 8001 --directory "$HOME/wheels" --bind 0.0.0.0 > /tmp/wheelserve.log 2>&1 &
sleep 2
curl -s -o /dev/null -w "local_serve: %{http_code}\n" "http://127.0.0.1:8001/$FNAME"
echo DONE
