#!/usr/bin/env python3
"""
carve_configs.py — 签名雕复：从 C3RB3R 加密卷的原始扇区里捞小配置文件片段。

仅适用于：文本类小配置文件（Home Assistant / clash / docker-compose / .env 等）
仍以明文残留在磁盘上、且该区域尚未被覆写的情况。

不是通用恢复工具。输出是 192 KiB 的原始窗口，需要人工从里面提取有用片段。

用法:
    python3 carve_configs.py --device /dev/sde --base 4832886784 --out ./hits

参数:
    --device   块设备，如 /dev/sde（只读打开）
    --base     btrfs 设备基点 = p3 字节偏移 + 14221312（Synology md data_offset）
               如果直接扫整盘（包含了分区表），填 0
    --out      输出目录
    --sigs     自定义签名文件（每行: 十六进制或明文<TAB>标签），不填用内置表
    --start    起始逻辑偏移（相对 base），默认 0
    --size     扫描长度，默认到设备末端
    --max-hits 每个签名最多存几次，默认 200

输出:
    <out>/<tag>_<offset>.bin     每个命中一个窗口（默认 64 KiB 前 + 128 KiB 后）
    <out>/hits.tsv               offset / tag / signature / file / size
"""
import argparse
import os
import sys
import time

# 内置签名表：(字节串, 标签)
# 只放"配置文件里稳定出现、且不太可能出现在二进制里"的短特征串。
DEFAULT_SIGS = [
    # Home Assistant
    (b'!include automations.yaml', 'ha'),
    (b'!include scripts.yaml',     'ha'),
    (b'!include_dir_named',        'ha'),
    (b'!include_dir_merge_named',  'ha'),
    (b'packages: !include',        'ha'),
    (b'customize: !include',       'ha'),
    (b'homeassistant:',            'ha'),
    # clash / mihomo
    (b'proxy-groups:',             'clash'),
    (b'rule-providers:',           'clash'),
    (b'external-controller:',      'clash'),
    (b'allow-lan:',                'clash'),
    (b'proxies:',                  'clash'),
    # docker-compose
    (b'services:',                 'compose'),
    (b'container_name:',           'compose'),
    (b'restart: unless-stopped',   'compose'),
    # 通用
    (b'BEGIN OPENSSH PRIVATE KEY', 'sshkey'),
    (b'BEGIN RSA PRIVATE KEY',     'sshkey'),
    (b'C3RB3R INSTRUCTIONS',       'ransom'),
]


def load_sigs(path):
    sigs = []
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.rstrip('\n')
            if not line or line.startswith('#'):
                continue
            if '\t' in line:
                pat, tag = line.split('\t', 1)
            else:
                pat, tag = line, 'custom'
            pat = pat.replace('\\t', '\t').replace('\\n', '\n')
            sigs.append((pat.encode('utf-8', 'surrogateescape'), tag))
    return sigs


def human(n):
    for u in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if n < 1024:
            return f'{n:.1f} {u}'
        n /= 1024
    return f'{n:.1f} PiB'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--device', required=True)
    ap.add_argument('--base', type=int, default=0)
    ap.add_argument('--out', required=True)
    ap.add_argument('--sigs')
    ap.add_argument('--start', type=int, default=0)
    ap.add_argument('--size', type=int, default=0)
    ap.add_argument('--max-hits', type=int, default=200)
    ap.add_argument('--win-before', type=int, default=64 * 1024)
    ap.add_argument('--win-after', type=int, default=128 * 1024)
    ap.add_argument('--block', type=int, default=16 * 1024 * 1024)
    ap.add_argument('--overlap', type=int, default=4096)
    args = ap.parse_args()

    sigs = load_sigs(args.sigs) if args.sigs else DEFAULT_SIGS
    os.makedirs(args.out, exist_ok=True)

    dev_size = os.lseek(os.open(args.device, os.O_RDONLY), 0, os.SEEK_END)
    end = args.base + args.size if args.size else dev_size
    if end > dev_size:
        end = dev_size
    total = end - args.base - args.start
    if total <= 0:
        print('扫描长度无效', file=sys.stderr)
        return 1

    print(f'设备      {args.device}  ({human(dev_size)})')
    print(f'btrfs 基点 {args.base}')
    print(f'扫描范围  {human(total)}  从 base+{args.start}')
    print(f'签名数    {len(sigs)}')
    print(f'输出      {args.out}')
    print()

    f = open(args.device, 'rb', buffering=0)
    log_path = os.path.join(args.out, 'hits.tsv')
    log_new = not os.path.exists(log_path)
    log = open(log_path, 'a', encoding='utf-8')

    hits = {s[0]: 0 for s in sigs}
    last_hit = {}
    done = 0
    n_hits = 0
    t0 = time.time()
    last_report = time.time()

    pos = args.start
    while pos < total:
        n = min(args.block + args.overlap, total - pos)
        if n <= 0:
            break
        f.seek(args.base + pos)
        buf = f.read(n)
        if not buf:
            break

        for sig, tag in sigs:
            if hits[sig] >= args.max_hits:
                continue
            # 精确遍历本缓冲区里所有出现位置（原版只取第一个，会漏）
            search = 0
            while True:
                i = buf.find(sig, search)
                if i < 0:
                    break
                search = i + 1
                abs_off = pos + i
                # 同一签名 256 KiB 内只取一次，避免同一段内容重复保存
                if abs_off - last_hit.get(sig, -10**12) < 256 * 1024:
                    continue
                last_hit[sig] = abs_off
                hits[sig] += 1
                n_hits += 1

                ws = max(args.start, pos + i - args.win_before)
                we = pos + i + args.win_after
                f.seek(args.base + ws)
                data = f.read(we - ws)
                name = f'{tag}_{abs_off:015d}.bin'
                outp = os.path.join(args.out, name)
                try:
                    with open(outp, 'wb') as o:
                        o.write(data)
                except OSError as e:
                    print(f'  写入失败 {e}', file=sys.stderr)
                    continue
                log.write(f'{abs_off}\t{tag}\t{sig.decode("utf-8", "replace")}\t{name}\t{len(data)}\n')
                log.flush()
                print(f'  命中 {tag:<8} {sig[:28].decode("utf-8","replace"):<30} @ {abs_off} -> {name}')
                if hits[sig] >= args.max_hits:
                    break

        step = min(args.block, total - pos)
        pos += step
        done += step

        now = time.time()
        if now - last_report >= 30:
            last_report = now
            el = now - t0
            rate = done / el if el else 0
            eta = (total - done) / rate / 3600 if rate else 0
            print(f'  {done * 100.0 / total:5.1f}%  {human(done)}/{human(total)}  '
                  f'{rate / 2**20:6.1f} MiB/s  ETA {eta:5.1f}h  命中 {n_hits}', flush=True)

    log.close()
    f.close()
    print()
    print(f'完成：扫描 {human(done)}，命中 {n_hits} 个窗口，耗时 {(time.time() - t0) / 60:.1f} 分钟')
    print(f'索引：{log_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
