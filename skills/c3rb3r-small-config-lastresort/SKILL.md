---
name: c3rb3r-small-config-lastresort
description: >
  【仅兜底 · 仅小文件】C3RB3R 勒索后的最后手段——从 Synology btrfs 磁盘的原始扇区里，
  按签名雕复出小体积文本配置文件的明文片段（Home Assistant、clash、docker-compose、SSH 私钥等）。
  只在其他办法都失败后才用：要求磁盘已拔出、目标区域未被覆写，产出是片段而非完整文件。
  不是通用恢复工具，救不回大文件，也救不回已被加密覆盖的内容。
  未关机请改用 soimy/c3rb3r-rescue；未全加密的大文件请改用 crt106/c3rb3r-btrfs-recovery。
---

# C3RB3R 小配置文件雕复（仅兜底 · 仅小文件）

## ⚠️ 先说清楚这个手段能做什么、不能做什么

**这是所有办法都试完之后，用来抢救"极少数几份关键小配置文件"的兜底手段。**

| 能 | 不能 |
|---|---|
| 捞回文本类小配置的**片段明文**（几百字节到几十 KiB） | 还原成完整可用的文件（输出是 192 KiB 原始窗口，要人工扒） |
| Home Assistant / clash / docker-compose / .env / SSH 私钥 | 加密后的文件（`.L0CK3D`）——那是密文，捞不出明文 |
| 磁盘**未被覆写**的情况 | 盘还在读写、还在跑系统的情况 |

**成功率完全取决于数据是否还在原位。** 一旦那些块被新数据覆盖，谁也救不回来。
实测中 **60 个 0x24 全加密的小文件（782 KB–1.6 MB）全部无法恢复** —— 它们的 extent 已被真正覆写。

---

## 一、先判断该用哪个工具

```
勒索软件刚跑完，NAS 还开着
    └──→ 别关机！改用  https://github.com/soimy/c3rb3r-rescue
          （趁内存里可能还有密钥/会话信息，优先抢这个）

盘已拔出，明文大文件还在（只是没加密完）
    └──→ 用  https://github.com/crt106/c3rb3r-btrfs-recovery
          （bookend extent 反推，能救回 99% 的 0x25/0x26 文件）

盘已拔出，只剩几份关键小配置想抢救
    └──→ 用本 skill（配置文件签名雕复）
```

**顺序不能颠倒。** 本 skill 是兜底，不是首选。

---

## 二、前置条件（缺一不可）

1. **磁盘必须已经从原机器上拔下来**，接在分析机上
2. **只读挂载/只读打开**，全程不得写入
3. 知道 btrfs 的**设备基点**（Synology 的算法见下）
4. 知道你要找的是什么文件 —— 必须能说出**特征字符串**

### 算 Synology 的 btrfs 设备基点

Synology 在数据分区上叠了一层 md，所以 btrfs 的起点不是 p3 偏移：

```
btrfs 基点 = p3 字节偏移 + md 的 data_offset(14221312)
```

查 p3 偏移：

```bash
cat /sys/block/sdX/sdX3/start        # 起始扇区
# 字节偏移 = 扇区数 × 512
```

实测例子（4 TB 盘）：

```
p3 起始扇区   9411456
p3 字节偏移   9411456 × 512        = 4818665472
+ md data_offset                     + 14221312
btrfs 基点                          = 4832886784   ← --base 填这个
```

> 已知参考值：6T 卷基点 `10890051584`，2T 冷备份基点 `4846059520`。
> **但每块盘都要自己算一遍**，不要套用。

---

## 三、怎么跑

```bash
python3 scripts/carve_configs.py \
    --device /dev/sde \
    --base   4832886784 \
    --out    ./carve_hits
```

只依赖 Python 3 标准库，不需要 root（只要能读块设备）。

### 常用参数

| 参数 | 说明 |
|---|---|
| `--sigs my.txt` | 自定义签名表，每行 `特征串<TAB>标签` |
| `--start N` | 从基点后第 N 字节开始扫（断点续扫用） |
| `--size N` | 扫描长度，默认到盘尾 |
| `--max-hits N` | 每个签名最多保存几次，默认 200 |
| `--win-before / --win-after` | 命中点前后各抓多少字节，默认 64 KiB / 128 KiB |

### 4 TB 盘的耗时参考

```
~140 MiB/s 机械盘直读 → 约 8 小时
建议挂后台跑：nohup ... &
```

---

## 四、签名怎么选（这是能不能捞到的关键）

**原则：选"配置文件里必然出现、且在二进制数据里几乎不可能出现"的短 ASCII 串。**

| 目标 | 推荐签名 |
|---|---|
| Home Assistant | `!include automations.yaml`、`!include_dir_named`、`packages: !include` |
| clash / mihomo | `proxy-groups:`、`rule-providers:`、`external-controller:` |
| docker-compose | `container_name:`、`restart: unless-stopped` |
| SSH 私钥 | `BEGIN OPENSSH PRIVATE KEY` |
| 通用 | 你自己服务里特有的字符串（域名、路径、注释） |

**不要用** `version:`、`name:`、`key:` 这种到处都有的短词，会命中几万个无关块。

---

## 五、结果怎么读

每次命中会存一个 `<标签>_<偏移>.bin`，是**命中点前 64 KiB 到后 128 KiB 的原始字节**。

```bash
# 先看哪个窗口里像是有完整内容
grep -a -n -A20 'proxy-groups:' ./carve_hits/clash_*.bin

# 直接提取文本片段
strings -n 8 ./carve_hits/ha_000546562027800.bin | less
```

**典型情况**：一个 192 KiB 窗口里，只有中间几百字节是你要的配置，前后都是别的文件的残留。
需要人工判断边界、拼回去。

`hits.tsv` 记录了每次命中的偏移、标签、签名和文件名，方便回溯。

---

## 六、实测数据（2026-10，4 TB Synology 单盘卷）

| 项 | 数值 |
|---|---|
| 扫描量 | 约 3.6 TiB DATA 区 |
| 耗时 | 约 5 小时（140 MiB/s） |
| 命中 | **47 个窗口 / 8.8 MB** |
| 有效内容 | 其中约一半能扒出可用的配置片段 |
| 失败案例 | **60 个 0x24 全加密小文件（782 KB–1.6 MB）全部救不回** |

**这组数字说明什么**：雕复只在"明文还在盘上、只是文件系统入口没了"时有效。
对于已经被加密覆盖的块，它无能为力 —— 这也是为什么它只能当兜底。

---

## 七、和另外两个工具的关系

| 项目 | 适用阶段 | 能力 |
|---|---|---|
| [soimy/c3rb3r-rescue](https://github.com/soimy/c3rb3r-rescue) | 机器还开着 | 抢密钥/内存残留 |
| [crt106/c3rb3r-btrfs-recovery](https://github.com/crt106/c3rb3r-btrfs-recovery) | 盘已拔出 | bookend extent 反推，恢复未全加密的大文件 |
| **本 skill** | 以上都做完后 | 少量关键小配置的兜底抢救 |

---

## 八、最后一句

**先试前两个项目。它们能救的是 99% 的文件，这个 skill 救的是剩下的边角。**

只有当你要找的东西恰好是「小、文本、极重要、且那块盘还没被写过」的时候，它才值得跑。
