# vlog-cut

> 给 Claude Code 用的「按文案剪辑」流水线 —— 长文案 + 素材池 → 自动剪出成片。

[![tests](https://github.com/hahadu4520/vlog-cut/actions/workflows/test.yml/badge.svg)](https://github.com/hahadu4520/vlog-cut/actions/workflows/test.yml)
![macOS](https://img.shields.io/badge/tested%20on-macOS-blue)
![python](https://img.shields.io/badge/python-3.10%2B-3776ab)
![license](https://img.shields.io/badge/license-PolyForm%20Noncommercial-purple)

一组 Claude Code skill：你给文案 + 一个素材文件夹，Claude 在 5 个检查点引导你出粗剪 + 中文字幕。每个关键节点 Claude 都会**主动停下等你确认**，不会一气呵成做错。

## 适合谁

- vlogger / 旅拍 / 解说类创作者，文案先行的工作流
- 接受「先粗剪，再去 Final Cut 精修」的人
- 本地优先，不想上传素材到云
- 当前**仅 macOS 测过**，Windows 几乎跑不了

## 上手

```bash
brew install ffmpeg
brew install --cask font-lxgw-wenkai          # 字幕默认字体
git clone https://github.com/hahadu4520/vlog-cut.git
cd vlog-cut && pip install -e .
bash install.sh                                # 检查依赖
```

然后在 Claude Code 里说人话：

> 我有一段文案和一堆视频素材，帮我做成视频

Claude 会触发 `vlog-cut-pipeline` skill 引导你。

📖 [完整教程](docs/tutorials/quick-start.md) · 🪲 [已知问题](docs/known-issues.md) · 🤝 [贡献](CONTRIBUTING.md)

## 路线图

- [x] **v0.1** pipeline + tts + index + narration-cut
- [x] **v0.2** burn-subtitles-cn（自动避开黑边）
- [x] **v0.4** align-narration（用户自带配音 → whisper 对齐）
- [ ] **v0.3** rotation 自动正方向 / 9:16 竖屏输出
- [ ] **v0.5** BGM 配乐
- [ ] **v1.0** Linux/Windows 实测 + PyPI

## License

**Source-available under [PolyForm Noncommercial 1.0.0](LICENSE).**

- ✅ 个人 / 学习 / 研究 / 业余项目：免费
- ❌ 商业用途、企业内部使用：需另购商业 license
- 📩 商业授权请联系：**微信 `duhh4520`**
