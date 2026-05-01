# vlog-cut

> Narration-driven video editing pipeline for Claude Code.
> 给 Claude Code 用的"按文案剪辑"流水线 —— 长文案 + 素材池 → 自动剪出成片。

## 演示

> 📺 _Demo video coming soon_

## 这是什么

vlog-cut 是一组 Claude Code skill，把"长文案 + 一堆视频素材 → 成片"这个流程拆成可控、可审核的几步：

1. **配音**：文案 → TTS（或你自己上传口播）
2. **素材索引**：让 Claude 看图，给每段视频打标签
3. **镜头分配**：按文案语义自动配镜头，先生成 timeline.json **等你审核**
4. **粗剪渲染**：ffmpeg 切片拼接 + 配音对齐
5. **字幕**（v0.2 起）：中文字幕分页 + 烧字幕

每个关键节点 Claude 会**主动停下**等你确认，**不会一气呵成做错**。

## 适合谁

- 风物 / 旅拍 / 解说类短视频创作者
- 想把固定流程自动化的 vlogger
- 文案先行、素材后配的工作方式

## 快速开始

```bash
# 1. 装依赖
brew install ffmpeg
pip install edge-tts
git clone <this repo> ~/vlog-cut

# 2. 在 Claude Code 里调用
> 我有一段文案和一些视频素材，想做成视频
# Claude 会触发 vlog-cut-pipeline skill，逐步引导你
```

详细教程：[docs/tutorials/quick-start.md](docs/tutorials/quick-start.md)

## 项目结构

```
skills/
├── vlog_cut_pipeline/      # 顶层编排，含 4 个强制审核检查点
├── tts_from_script/        # 文案 → 配音 + 时间戳
├── align_narration/        # 自带配音 → whisper 对齐 + 时间戳
├── video_asset_index/      # 视频目录 → 素材索引
└── narration_cut/          # timeline 规划 + 校验 + 渲染（plan/validate/render）

shared/schemas/             # 数据契约（timing/assets/timeline JSON schema）
shared/ffmpeg_helpers.py    # ffmpeg/ffprobe 薄封装
docs/                       # 教程、架构、常见问题
```

> 目录使用下划线（Python 包命名要求），SKILL.md 仍按 `name: vlog-cut-pipeline` 等连字符标识对外暴露 skill 名。

## 设计原则

1. **数据契约优先**：`timing.json` / `assets_index.json` / `timeline.json` 三个 JSON schema 是 skill 之间的协议。任何人写一个新的 TTS 引擎或素材索引器，只要符合 schema，就能接进来。

2. **强制审核检查点**：4 个关键节点 Claude 必须停下等你确认（试听配音、审 timeline、看粗剪、看字幕预览）。这是从真实项目经验里总结的——AI 一气呵成多半要返工，让人审才省时间。

3. **每个 skill 独立可用**：不想走整套流程？直接调单个 skill 也行。

## 路线图

- [x] **v0.1**：pipeline + tts-from-script + video-asset-index + narration-cut
- [x] **v0.4**（提前）：align-narration（用户自带配音 → whisper 对齐）
- [ ] **v0.2**：burn-subtitles-cn（中文字幕）
- [ ] **v0.3**：rotation 检测 / 重复扫描的自动修复建议
- [ ] **v1.0**：完整文档、tutorials、test fixtures

## License

MIT
