# C3RB3R 小配置文件雕复（仅兜底 · 仅小文件）

> **这不是通用恢复工具。**
> 它只在其他办法都失败后使用，只对**小体积文本配置文件**有效，
> 且要求**磁盘已拔出、目标区域尚未被覆写**。
> 产出是**片段**（192 KiB 原始窗口），需要人工从中提取，不会得到完整文件。

C3RB3R 勒索软件会加密 Synology NAS 上的文件。在**极端情况**下——大文件已经
被别的办法救完、只剩几份关键的小配置（Home Assistant、clash、docker-compose、
SSH 私钥）——可以用签名雕复从原始扇区里把它们的明文片段捞出来。

---

## 先判断该用哪个工具

```
勒索软件刚跑完，NAS 还开着
    └──→ 别关机！改用  https://github.com/soimy/c3rb3r-rescue

盘已拔出，明文大文件还在（只是没加密完）
    └──→ 用  https://github.com/crt106/c3rb3r-btrfs-recovery

以上都做完了，只剩几份小配置想抢救
    └──→ 用本工具（兜底）
```

**顺序不能颠倒。**

---

## 能做什么 / 不能做什么

| 能 | 不能 |
|---|---|
| 捞回文本类小配置的**片段明文**（几百字节 ~ 几十 KiB） | 还原成完整可用的文件 |
| Home Assistant / clash / docker-compose / `.env` / SSH 私钥 | 加密后的文件（`.L0CK3D`）——那是密文 |
| 磁盘**未被覆写**时 | 盘还在读写、系统还在跑时 |

实测中，60 个全加密（0x24 模式）的小文件（782 KB – 1.6 MB）**全部无法恢复** ——
它们的 extent 已被真正覆写。雕复对这类情况无能为力。

---

## 快速开始

```bash
# 1) 算 btrfs 设备基点（Synology 叠了 md，不是 p3 偏移）
#    base = p3 字节偏移 + 14221312
cat /sys/block/sdX/sdX3/start        # 起始扇区 → ×512 = 字节偏移

# 2) 跑雕复（纯标准库，不需 root，只要能读块设备）
python3 skills/c3rb3r-small-config-lastresort/scripts/carve_configs.py \
    --device /dev/sde \
    --base   4832886784 \
    --out    ./carve_hits
```

4 TB 盘约 8 小时（140 MiB/s 直读），建议挂后台。

### 常用参数

| 参数 | 说明 |
|---|---|
| `--sigs my.txt` | 自定义签名表，每行 `特征串<TAB>标签` |
| `--start N` | 断点续扫 |
| `--max-hits N` | 每个签名最多存几次（默认 200） |
| `--win-before` / `--win-after` | 命中点前后各抓多少字节（默认 64 KiB / 128 KiB） |

---

## 签名怎么选

**选"配置文件里必然出现、二进制数据里几乎不可能出现"的短 ASCII 串。**

好的签名：`!include automations.yaml`、`proxy-groups:`、`BEGIN OPENSSH PRIVATE KEY`

不要用：`version:`、`name:`、`key:` —— 会命中几万个无关块。

---

## 结果怎么读

每次命中存一个 `<标签>_<偏移>.bin`，是命中点前 64 KiB 到后 128 KiB 的原始字节。

```bash
grep -a -n -A20 'proxy-groups:' ./carve_hits/clash_*.bin
strings -n 8 ./carve_hits/ha_000546562027800.bin | less
```

`hits.tsv` 记录每次命中的偏移、标签、签名、文件名。

**典型情况**：192 KiB 窗口里只有中间几百字节有用，前后都是其他文件的残留，
需要人工判断边界。

---

## 自测

```bash
bash skills/c3rb3r-small-config-lastresort/test_carve.sh
```

会造一个 4 MiB 假镜像，埋入 4 个签名，验证偏移与内容都对得上。

---

## 实测数据（4 TB Synology 单盘卷）

| 项 | 数值 |
|---|---|
| 扫描量 | 约 3.6 TiB 数据区 |
| 耗时 | 约 5 小时（140 MiB/s） |
| 命中 | 47 个窗口 / 8.8 MB |
| 有效 | 约一半能扒出可用片段 |
| 失败 | 60 个 0x24 全加密小文件，全部救不回 |

这组数字说明：雕复只在"明文还在盘上、只是文件系统入口没了"时有效。

---

## 许可

MIT
