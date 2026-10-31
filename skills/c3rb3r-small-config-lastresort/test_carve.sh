#!/bin/bash
# 冒烟测试：造一个带签名的假镜像，验证雕复逻辑
# 用法: bash test_carve.sh
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${TMPDIR:-/tmp}/cartest"

rm -rf "$WORK"
mkdir -p "$WORK/out"

python3 - "$WORK/fake.img" <<'PY'
import sys
size = 4 * 1024 * 1024
buf = bytearray(size)
buf[500_000:500_000 + 13]     = b'proxy-groups:'
buf[1_500_000:1_500_000 + 27] = b'!include automations.yaml'
buf[3_000_000:3_000_000 + 23] = b'BEGIN OPENSSH PRIVATE KEY'
buf[3_500_000:3_500_000 + 8]  = b'proxies:'
with open(sys.argv[1], 'wb') as f:
    f.write(bytes(buf))
print(f'test image 4 MiB -> {sys.argv[1]}')
PY

python3 "$HERE/scripts/carve_configs.py" \
    --device "$WORK/fake.img" --base 0 --out "$WORK/out" --block 1048576

echo
echo "=== 输出文件 ==="
ls -la "$WORK/out/"

echo
echo "=== 索引 ==="
cat "$WORK/out/hits.tsv"

echo
echo "=== 验证抓到的内容 ==="
rc=0
for f in "$WORK"/out/*.bin; do
    found=$(grep -a -o -m1 -E 'proxy-groups:|proxies:|!include automations.yaml|BEGIN OPENSSH PRIVATE KEY' "$f" || true)
    if [ -n "$found" ]; then
        echo "  OK   $(basename "$f"): $found"
    else
        echo "  FAIL $(basename "$f")"
        rc=1
    fi
done

echo
if [ "$rc" -eq 0 ]; then
    echo "冒烟测试通过"
else
    echo "冒烟测试失败"
fi
exit "$rc"
