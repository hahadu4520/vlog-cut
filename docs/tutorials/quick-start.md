# Quick Start：5-10 分钟做一支带字幕的 vlog

这篇用我们 dogfood 时做的「**AI 时代多散步才是正经事**」散步 vlog 当例子，带你走一遍完整流程。

## 你需要准备

- macOS（其它系统未测）
- 1 段你录的口播音频（`.m4a` / `.mp3` / `.wav` 都行），或者一份待 TTS 的文案
- 一个文件夹，里面装 5-20 段相关的视频素材（`.mp4` / `.mov` 都行）
- Claude Code 已经装好，能进入项目目录

## 装一次依赖

```bash
brew install ffmpeg
pip install openai-whisper           # 仅当用自己录的口播
git clone <this-repo> ~/vlog-cut
cd ~/vlog-cut
pip install -e .

# 字体（默认 LXGW WenKai；其它可选见 README）
brew install --cask font-lxgw-wenkai
```

或者：`bash install.sh` 会一并检查 + 提示缺啥。

## 跟 Claude 说人话

进 Claude Code 进入项目目录（或者任何目录都行，反正 vlog-cut CLI 全局可用），说：

> 我有一段口播 `~/我的口播.m4a` 和素材文件夹 `~/Downloads/clips/`，文案是「AI 时代多散步才是正经事」，帮我做成视频。

Claude 会触发 `vlog-cut-pipeline` skill，按 5 个检查点引导你。

## 5 个检查点是什么

完整流程分 5 段，每段做完 Claude 会停下来等你确认：

| 段 | Claude 自动做 | 你审核什么 |
|---|---|---|
| **A. 配音** | 跑 TTS 或对齐你的录音 → 出 `narration.wav` + `timing.json` | 听一下，语速 / 错字对不对 |
| **B. 素材索引** | ffmpeg 抽帧 → 给每段视频做 contact sheet → Claude 看图打标签 | 标签准不准、哪些素材该标 unusable |
| **C. timeline** | 算法给每句文案配镜头 → Claude 读 sheets 手工调整 | 看 timeline.json，哪个镜头不对换一下 |
| **D. 粗剪** | ffmpeg 切片 → concat → mux 配音 → 出 `rough_cut.mp4` | 看视频，画面是否对得上音 |
| **E. 字幕（可选）** | 按句子分页 → 生成 .ass → 烧到视频上 | 看字幕断句、字号、位置 |

每个 STOP 都是明确的：Claude 会说「现在请你审核 X，OK 后说"继续"」。

## 实例：散步 vlog 实跑

我们走一遍真实的 dogfood 流程作为例子。

### 准备物料

```
~/Downloads/0501testvideo/
├── 口播.m4a                  # 你录的（55 秒）
├── IMG_1578.mov              # 16 段素材（机场玻璃顶 / 雨车窗 / 火锅 / 山顶咖啡 ...）
├── IMG_1608.MOV
├── ...
```

文案（贴给 Claude）：

```
AI 时代多散步才是正经事。
最近就发现 AI 越好用，我越想出门散步。
以前下楼是去办事，现在下楼，单纯就是想走一走。
...
```

### 跟 Claude 说

> 我录了口播 `~/Downloads/0501testvideo/口播.m4a`，素材在同一个文件夹，文案我贴给你。帮我做成视频。

### 阶段 A：配音

Claude 探测到你给了 `.m4a`（不是文案），所以触发 `align-narration`：

```bash
vlog-cut-align --audio ~/Downloads/0501testvideo/口播.m4a \
               --script ~/Downloads/0501testvideo/script.json \
               --out ~/Downloads/0501testvideo/proj
```

输出：`timing.json`（每段对应录音的哪段时间）+ `narration.wav`（标准化的音频）。

🛑 **检查点 1**：你听一下原口播，确认 timing.json 里 5 段的边界对得上你的录音节奏。错了可以让 Claude 调 script.json 里每段的 `head_text` 重跑。

### 阶段 B：素材索引

```bash
vlog-cut-index --src ~/Downloads/0501testvideo --out ~/Downloads/0501testvideo/proj
```

每段视频抽 3 帧，拼成一张 contact sheet（`proj/sheets/IMG_xxxx.jpg`）。Claude 用 Read 工具看每张 sheet，给 `assets_index.json` 加 scene / tags / chapters / usable 字段。

🛑 **检查点 2**：你看一下 `assets_index.json`，确认：
- 哪些素材标了 `usable: false`，对不对（比如方向坏了的）
- `chapters` 字段对不对（intro / scene / reason / outro）
- 有没有重要素材被漏标

### 阶段 C：timeline

```bash
vlog-cut-plan --timing proj/timing.json --assets proj/assets_index.json \
              --out proj/timeline.json --size 1920x1080 --fps 30
```

算法给每段口播配镜头。然后 Claude 自己读一遍 timeline，看哪些镜头分配奇怪，**手工改 timeline.json**（这一步是 Claude 主动做，不是 plan 命令做）。

```bash
vlog-cut-validate --timeline proj/timeline.json --src ~/Downloads/0501testvideo \
                  --timing proj/timing.json
# 必须 exit 0（clean），exit 1 是有 warning 但能继续，exit 2 必须修
```

🛑 **检查点 3**：审 timeline.json。
- 同一段素材重复出现没？（散步 vlog 时我让 IMG_4857 出现了 5 次，太单调）
- 食物镜头集中在 reason 段、风景集中在 outro 段，对不对？

让 Claude 调，每改一次重新 validate。

### 阶段 D：粗剪渲染

```bash
vlog-cut-render --timeline proj/timeline.json --timing proj/timing.json \
                --src ~/Downloads/0501testvideo \
                --narration proj/narration.wav \
                --out proj --name rough_cut.mp4
```

ffmpeg 一段一段切，concat 起来，mux 上配音。50 秒视频在 M1 mac 上大约 30 秒-1 分钟。

🛑 **检查点 4**：`open proj/rough_cut.mp4` 看一遍。
- 画面跟音同不同步？
- 镜头切换有没有突兀的？
- 音频末尾有没有被截？（我们修过这个 bug，render 现在会主动 warn）

### 阶段 E：字幕

```bash
vlog-cut-subs-split --timing proj/timing.json --script proj/script.json \
                    --out proj/subs_pages.json --max-chars 12

vlog-cut-subs-build --pages proj/subs_pages.json \
                    --video proj/rough_cut.mp4 \
                    --out proj/subtitles.ass

vlog-cut-subs-burn --video proj/rough_cut.mp4 --subs proj/subtitles.ass \
                   --out proj/rough_cut_subs.mp4
```

注意：
- `--script` 让字幕用你写的有标点版本（而不是 whisper 转的无标点版本）
- `--video` 让 subs-build 自动检测黑边，自动收紧字号

🛑 **检查点 5**：看 `rough_cut_subs.mp4`，字幕字号 / 位置 / 断句对不对。

## 常见问题

### Q：我没有口播，能用 TTS 吗？
能。把第一阶段从 `vlog-cut-align` 换成 `vlog-cut-tts`：
```bash
vlog-cut-tts --script proj/script.json --out proj
```
script.json 写每段的文字，会用 edge-tts 合成。**默认 voice 是 zh-CN-XiaoyiNeural**。

### Q：renderer 能不能输出 9:16 竖屏？
当前不行（v0.3 路线图）。现在所有素材会被 pad 到 16:9，竖屏素材两边有黑边。字幕已经会自动避开黑边。

### Q：whisper 要不要 GPU？
不要。CPU 跑 50 秒音频用 large-v3-turbo 模型大约 1-2 分钟。模型首次自动下载约 1.5GB。

### Q：可以不让 Claude 介入，纯命令行跑吗？
可以。每个 CLI 都能独立跑。但你得自己写 timeline.json 这种"创意活"。Claude 的价值在于「读 sheets 决定哪个镜头配哪句话」+「在每个检查点等你审」。

### Q：bug 怎么报？
[docs/known-issues.md](../known-issues.md) 看看是不是已知。如果不是，开 GitHub issue，附上：
- 哪一步出错（A/B/C/D/E）
- 完整命令行 + 报错
- `proj/state.json` 内容（如果存在）

## 参考

- [docs/known-issues.md](../known-issues.md) — dogfood 找出的 10 个 bug 复盘
- 项目根 [README.md](../../README.md) — 全貌
- 各 skill 的 SKILL.md — 单独 CLI 的全部参数
