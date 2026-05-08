# vlog-cut

> 一段口播 + 一个素材文件夹 → 带中文字幕的成片，全程在你审下推进。

[![tests](https://github.com/hahadu4520/vlog-cut/actions/workflows/test.yml/badge.svg)](https://github.com/hahadu4520/vlog-cut/actions/workflows/test.yml)
![macOS](https://img.shields.io/badge/tested%20on-macOS-blue)
![python](https://img.shields.io/badge/python-3.10%2B-3776ab)
![license](https://img.shields.io/badge/license-PolyForm%20Noncommercial-purple)

https://github.com/user-attachments/assets/80b98d9b-40f7-4740-a26a-c278525d0ebd

> 上面是用 vlog-cut 做的一支 200 秒云南寻甸 vlog（[原画质下载](https://github.com/hahadu4520/vlog-cut/releases/download/demo/yunnan-demo.mp4)）。

vlog-cut 是一组 Claude Code skill。你给 Claude 文案和素材，它在 5 个关键节点停下让你审 —— 配音对不对、镜头选得好不好、字幕断句顺不顺 —— 不会一气呵成做错。

## 能做什么

- 🎙️ **配音** —— TTS 合成（edge-tts）或对齐你自己的录音（whisper）
- 🏷️ **素材打标** —— Claude 看每段视频的关键帧，自动写场景标签
- 🎬 **按文案剪辑** —— 算法配镜头 + Claude 微调，**你确认后才渲染**
- 🔤 **中文字幕** —— 标点感知断句、4 款手写字体可选、自动避开黑边
- 🛡️ **5 个审核检查点** —— 每一步都能改，不会全跑完才发现错

## 适合谁

- vlogger、旅拍、解说类创作者，文案先行
- 接受「先粗剪、再去 Final Cut 精修」的工作流
- 本地优先，不想上传素材到云
- 目前在 macOS 上工作得最好

## 上手 30 秒

```bash
brew install ffmpeg
brew install --cask font-lxgw-wenkai          # 字幕默认字体
git clone https://github.com/hahadu4520/vlog-cut.git
cd vlog-cut && pip install -e .
```

打开 Claude Code，说：

> 我有一段文案和一堆视频素材，帮我做成视频

剩下的交给 Claude，它会按 5 个检查点引导你。**完整教程：[5 分钟跑通一支 vlog](docs/tutorials/quick-start.md)**。

## License

**[PolyForm Noncommercial 1.0.0](LICENSE)**

- ✅ 个人 / 学习 / 业余项目：免费
- 💼 商业或企业内部使用：请购买商业 license，**微信 `duhh4520`**
