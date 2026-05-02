# vlog-cut

> Narration-driven video editing pipeline for Claude Code.
> 给 Claude Code 用的"按文案剪辑"流水线 —— 长文案 + 素材池 → 自动剪出成片。

[![tests](https://github.com/hahadu4520/vlog-cut/actions/workflows/test.yml/badge.svg)](https://github.com/hahadu4520/vlog-cut/actions/workflows/test.yml)
![macOS-tested](https://img.shields.io/badge/tested%20on-macOS-blue)
![python](https://img.shields.io/badge/python-3.10%2B-3776ab)
![license](https://img.shields.io/badge/license-MIT-green)

## 演示

> 📺 _Demo gif coming soon — will be linked here from a GitHub release attachment._

50 秒，从 16 段素材 + 一段口播 + 一份文案 → 1080p 带中文字幕的成片。整个过程 Claude 在 5 个检查点停下让你审，不会一气呵成做错。

## 这是什么

vlog-cut 是一组 Claude Code skill，把"长文案 + 一堆视频素材 → 成片"这个流程拆成可控、可审核的几步：

1. **配音**：文案 → TTS（或你自己上传口播 → whisper 对齐）
2. **素材索引**：让 Claude 看图，给每段视频打标签
3. **镜头分配**：按文案语义自动配镜头，先生成 timeline.json **等你审核**
4. **粗剪渲染**：ffmpeg 切片拼接 + 配音对齐
5. **字幕**：中文字幕分页 + 烧字幕（自动避开黑边）

每个关键节点 Claude 会**主动停下**等你确认，**不会一气呵成做错**。

## 适合谁

**适合**：
- **vlogger / 旅拍 / 风物 / 解说类创作者** —— 文案先行、素材后配的工作流
- **想把固定流程自动化的人** —— 同一套节奏（开头钩子 / 场景 / 道理 / 收尾）反复用
- **接受"先粗剪再精修"的人** —— 工具出粗剪，你拿到 Final Cut / DaVinci 里精修
- **本地优先的人** —— 不愿意把素材传云端，所有处理在本地完成
- **会跟 Claude Code 协作的人** —— 不需要写代码，但需要会跟 Claude 描述需求

**不适合**：
- **追求电影级精剪的人** —— 这工具不做调色 / 转场 / 关键帧动画 / 多轨混音
- **完全不愿审核的人** —— 4-5 个 STOP 点等你确认；想一键出片去用别的
- **只剪一两段的人** —— 装环境的成本（ffmpeg + whisper + Python + 字体）不划算
- **Windows 用户** —— 当前只在 macOS 测过，Linux 可能能跑，Windows 几乎肯定不行（路径转义问题）
- **不会描述需求的人** —— 你得有文案、有素材文件夹、能用大白话告诉 Claude 段落怎么分

## 现状

- ✅ 在 macOS 上反复 dogfood 过（散步 vlog 项目从头到尾走过完整流程，每个 bug 都修了 + 加了 regression 测试）
- ⚠️ 仅 macOS 测过；Linux 应该可以跑（CI 在 Ubuntu 上测代码逻辑），Windows 没测
- ⚠️ 中文字幕模块（split / 字体推荐）针对中文优化；其他语言能用但效果未调

## 快速开始

```bash
# 1. 装系统依赖（一次性）
brew install ffmpeg                            # 视频剪辑核心
pip install openai-whisper                     # 仅当需要"用户自带配音"对齐时用

# 2. clone + 装项目
git clone <this repo> ~/vlog-cut
cd ~/vlog-cut
pip install -e .

# 3. 装中文字体（4 选 1 或全装；用于字幕）
brew install --cask font-lxgw-wenkai           # 霞鹜文楷 - 手写楷体（默认）
brew install --cask font-lxgw-marker-gothic    # 霞鹜马克手写 - 马克笔风格
brew install --cask font-smiley-sans           # 得意黑 - 圆润现代
brew install --cask font-ma-shan-zheng         # 马善政毛笔 - 毛笔书法

# 4. 在 Claude Code 里说人话
> 我有一段文案和一堆视频素材，帮我做成视频
# Claude 会触发 vlog-cut-pipeline skill，按 5 个检查点引导你
```

或者跑 `bash install.sh` 一键检查 + 安装所有依赖。

**详细教程**：[docs/tutorials/quick-start.md](docs/tutorials/quick-start.md)

## 项目结构

```
skills/
├── vlog_cut_pipeline/      # 顶层编排，含 5 个强制审核检查点
├── tts_from_script/        # 文案 → 配音 + 时间戳
├── align_narration/        # 自带配音 → whisper 对齐 + 时间戳
├── video_asset_index/      # 视频目录 → 素材索引
├── narration_cut/          # timeline 规划 + 校验 + 渲染（plan/validate/render）
└── burn_subtitles_cn/      # 中文字幕分页 + ASS + 烧字幕（split/build/burn）

shared/schemas/             # 数据契约（5 个 JSON schema）
shared/ffmpeg_helpers.py    # ffmpeg/ffprobe 薄封装
docs/known-issues.md        # dogfood 中发现的 bug 复盘
docs/tutorials/             # 用户教程
```

> 目录使用下划线（Python 包命名要求），SKILL.md 仍按 `name: vlog-cut-pipeline` 等连字符标识对外暴露 skill 名。

## 设计原则

1. **数据契约优先**：`timing.json` / `assets_index.json` / `timeline.json` / `subs_pages.json` 是 skill 之间的协议。任何人写一个新的 TTS 引擎或素材索引器，只要符合 schema，就能接进来。

2. **强制审核检查点**：5 个关键节点 Claude 必须停下等你确认（试听配音、审标签、审 timeline、看粗剪、看字幕预览）。这是从真实项目经验里总结的——AI 一气呵成多半要返工，让人审才省时间。

3. **每个 skill 独立可用**：不想走整套流程？直接调单个 CLI（`vlog-cut-tts` / `vlog-cut-align` / `vlog-cut-index` / `vlog-cut-plan` / `vlog-cut-validate` / `vlog-cut-render` / `vlog-cut-subs-split` / `vlog-cut-subs-build` / `vlog-cut-subs-burn`）也行。

4. **本地优先**：所有处理（除 TTS 用 edge-tts 联网生成 + whisper 首次下载模型）都在本地。素材不上传任何云。

## 路线图

- [x] **v0.1**：pipeline + tts-from-script + video-asset-index + narration-cut
- [x] **v0.2**：burn-subtitles-cn（中文字幕：split / build / burn，自动避开黑边）
- [x] **v0.4**（提前完成）：align-narration（用户自带配音 → whisper 对齐）
- [ ] **v0.3**：rotation 元数据自动正方向 / 输出 9:16 竖屏支持
- [ ] **v0.5**：BGM 配乐（mix 工具 + 可选 MusicGen 本地生成）
- [ ] **v1.0**：跨平台测试（Linux 实测、Windows 路径修复）+ PyPI 发布

## 贡献

欢迎 PR / issue。具体见 [CONTRIBUTING.md](CONTRIBUTING.md)：
- 怎么本地跑测试
- 加 skill 的约定
- bug 报告 / PR 检查清单

## License

MIT
