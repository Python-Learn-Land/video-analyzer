# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 提供在操作此代码仓库时的指导。

## 项目概览

一个 Python CLI 工具，使用视觉大语言模型（Ollama 或 OpenAI 兼容 API，如 OpenRouter）和 OpenAI Whisper 进行音频转录来分析视频。它从视频中提取关键帧，用视觉模型逐帧分析（携带前几帧的滚动上下文），并将帧笔记与转录文本合成为最终的视频描述。

本仓库包含三个子包：
- **video-analyzer** —— 核心 CLI 工具 (`video_analyzer/`)
- **video-analyzer-tune** —— 基于 DSPy MIPROv2 的提示词优化器 (`video-analyzer-tune/`)
- **video-analyzer-ui** —— 轻量级 Flask Web 界面 (`video-analyzer-ui/`)

## 开发命令

以开发模式安装核心包：
```bash
pip install -e .
```

以同样方式安装子包：
```bash
cd video-analyzer-tune && pip install -e .
cd video-analyzer-ui && pip install -e .
```

运行分析器：
```bash
# 本地使用 Ollama（默认）
video-analyzer video.mp4

# 使用 OpenAI 兼容 API
video-analyzer video.mp4 --client openai_api --api-key KEY --api-url https://openrouter.ai/api/v1

# 保留帧、限制帧数、自定义提示词
video-analyzer video.mp4 --keep-frames --max-frames 10 --prompt "视频中展示了什么活动？"
```

运行提示词加载测试：
```bash
python test_prompt_loading.py
```

运行 UI 开发服务器：
```bash
video-analyzer-ui --dev
```

## 架构

### 三阶段流水线 (cli.py)

1. **帧提取与音频处理** —— `VideoProcessor` 使用 OpenCV 提取关键帧（基于帧差异分数的自适应采样）。`AudioProcessor` 通过 FFmpeg 提取音频，并使用 `faster-whisper` 进行转录。
2. **帧分析** —— `VideoAnalyzer.analyze_frame()` 将每帧图像 + 之前的分析结果发送给视觉大语言模型。帧笔记通过 `{PREVIOUS_FRAMES}` 提示词令牌按时间顺序累积。
3. **视频重建** —— `VideoAnalyzer.reconstruct_video()` 将所有帧笔记 + 转录文本输入到最终合成提示词中（`{FRAME_NOTES}`、`{TRANSCRIPT}`、`{FIRST_FRAME}` 令牌）。

### 配置级联 (config.py)

优先级（从高到低）：
1. 命令行参数
2. 用户配置 (`config/config.json`)
3. 默认配置 (`video_analyzer/config/default_config.json`)

关键配置段：`clients`（ollama 或 openai_api）、`frames`（per_minute, max_count）、`audio`（whisper_model, device, language）、`prompts`（提示词名称/路径条目列表）、`prompt_dir`（自定义提示词目录）。

### 提示词系统 (prompt.py)

两个通过索引访问的固定提示词槽位：
- 索引 0：帧分析提示词 (`frame_analysis/frame_analysis.txt`)
- 索引 1：视频重建提示词 (`frame_analysis/describe.txt`)

提示词文件支持令牌替换：`{PREVIOUS_FRAMES}`、`{FRAME_NOTES}`、`{TRANSCRIPT}`、`{FIRST_FRAME}`、`{prompt}`（用户的 `--prompt` 问题前缀为 "I want to know"）。

`PromptLoader` 按以下顺序解析提示词文件：用户指定的 `prompt_dir` → 包资源 (`pkg_resources`) → 包目录。这允许用户在不修改包的情况下覆盖提示词。

### 大语言模型客户端抽象 (clients/)

- `LLMClient` —— 抽象基类，包含 `encode_image()`（base64）和 `generate()`
- `OllamaClient` —— 本地 Ollama API，在 `images` 数组中发送图片
- `GenericOpenAIAPIClient` —— OpenAI 兼容 API（OpenRouter、OpenAI 等），以 `image_url` 内容形式发送图片，具有速率限制重试逻辑

### 帧选择算法 (frame.py)

1. 根据视频时长 × `frames_per_minute` 计算目标帧数，受 `max_frames` 限制
2. 以间隔 = total_frames / (target × 2) 进行采样以找到候选帧
3. 通过与前一帧的灰度绝对差值评分候选帧，阈值 10.0
4. 取前 N 个最高分，按时间顺序重新排序，如果设置了 `max_frames` 则可选均匀子采样

## 代码风格与审查规则

来自 `.github/pr-reviewer-config.yml`，AI PR 审查器强制执行：

- `video_analyzer/` 中所有公共函数必须有**类型提示**
- 必须与现有 **CLI 接口、配置文件 schema 和输出 JSON schema** 保持**向后兼容**
- 文件 I/O 和网络调用必须有**错误处理**
- 没有 `requirements.txt` 条目不得添加**新的硬依赖**（使用 `>=` 而非 `==`）
- **版本固定**必须使用 `>=`，条件标记必须是有效的 PEP 508
- `setup.py` 中的 `python_requires` 和 `install_requires` 必须与 `requirements.txt` 和 README（Python 3.11+）保持同步
- CI/工作流变更：不得回显 secrets、权限遵循最小特权原则、Actions 步骤必须固定到 SHA 或标记版本

## PR 审查机器人

本仓库有一个 AI PR 审查器 (`.github/scripts/pr_reviewer.py`)，通过 `.github/workflows/pr-review.yml` 在每个 PR 上运行。它通过 GitHub API 从默认分支获取脚本——无需 checkout。该脚本使用 OpenRouter（默认 `qwen/qwen3-235b-a22b`，可通过 `REVIEW_MODEL` 仓库变量配置）。审查配置在 `.github/pr-reviewer-config.yml` 中。

## 重要文件路径

- 核心包：`video_analyzer/` —— analyzer、cli、config、frame、audio_processor、prompt
- 客户端：`video_analyzer/clients/` —— llm_client、ollama、generic_openai_api
- 默认配置：`video_analyzer/config/default_config.json`
- 包提示词：`video_analyzer/prompts/frame_analysis/`
- 用户配置：`config/config.json`
- 测试：`test_prompt_loading.py`（核心）、`video-analyzer-tune/tests/`（tune 子包）
- 依赖：`requirements.txt`（核心）、`video-analyzer-tune/requirements.txt`、`video-analyzer-ui/requirements.txt`

## 贡献注意事项

- 遵循 PEP 8，使用类型提示，保持函数聚焦
- 使用约定式提交：`feat:`、`fix:`、`docs:`、`test:`、`chore:`
- 在打开 PR 之前先在 GitHub Discussions 中提出变更建议
- PR 审查机器人会标记范围蔓延、缺少测试计划、不合理的依赖和向后兼容性破坏
