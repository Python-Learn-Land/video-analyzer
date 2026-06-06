# video-analyzer-tune

基于 DSPy 的提示词优化器，用于 [video-analyzer](https://github.com/byjlw/video-analyzer)。

根据你的特定内容和用例的理想输出示例，自动优化 `video-analyzer` 使用的两个提示词 —— 逐帧分析提示词和最终视频重建提示词。

## 概述

`video-analyzer` 分两个阶段工作：逐帧分析每个视频帧（构建持续运行的观察日志），然后将所有帧笔记合成为最终的视频描述。两个阶段都由可自定义的提示词文件驱动。

`video-analyzer-tune` 使用 [DSPy MIPROv2](https://dspy.ai) 端到端优化两个提示词。你提供一些理想输出的示例 —— 包括帧级别和最终描述级别 —— 优化器会自动找到更好的提示词指令。

主 `video-analyzer` 包完全不受影响。优化后的提示词会写入新文件，你通过配置指向这些文件即可。

## 环境要求

- Python 3.8+
- `video-analyzer >= 0.1.1`
- Ollama 实例（需安装视觉模型）或兼容 OpenAI 的 API

## 安装

```bash
pip install video-analyzer-tune
```

## 快速开始

### 第一步 —— 生成输出并保留帧

在代表性视频上运行 `video-analyzer` 并保留提取的帧：

```bash
video-analyzer my_video.mp4 --keep-frames
```

这会生成一个 `output/` 目录，包含：
- `analysis.json` —— 元数据和最终视频描述
- `transcript.json` —— 音频转录文本
- `frame_analyses.json` —— 逐帧分析笔记
- `frames/` —— 提取的帧图像

### 第二步 —— 用理想输出编辑相关文件

编辑以下文件中的理想输出：

**必填：** 编辑 `analysis.json` 中的 `video_description.response`，展示你的用例下理想最终描述的样子。

**推荐：** 编辑 `frame_analyses.json` 中每个条目的 `response`，展示理想的帧笔记样子。这为流水线的两个阶段都提供了优化信号，能产生更好的结果。

```json
// frame_analyses.json
[
  {
    "frame": 0,
    "timestamp": 0.0,
    "response": "你的理想帧笔记写在这里 —— 哪些细节对你的用例重要"
  }
]

// analysis.json
{
  "video_description": {
    "response": "你的理想最终描述写在这里 —— 你想要的风格、长度和关注点"
  }
}
```

你编辑并作为训练示例包含的视频越多，结果就越好。

### 第三步 —— 创建 training_data.json

```json
{
  "examples": [
    { "output_dir": "output" }
  ]
}
```

每编辑一个视频就添加一个条目：

```json
{
  "examples": [
    { "output_dir": "output/video1" },
    { "output_dir": "output/video2" },
    { "output_dir": "output/video3" }
  ]
}
```

### 第四步 —— 运行优化器

```bash
video-analyzer-tune --training-data training_data.json --output-dir tuned_prompts/
```

这会运行 MIPROv2 优化，耗时取决于 `--num-candidates` 和 `--num-trials` 的设置。

### 第五步 —— 更新你的配置

优化完成后，工具会打印一段配置片段，你可以粘贴到 `config/config.json` 中：

```json
"prompt_dir": "tuned_prompts",
"prompts": [
  {"name": "Frame Analysis", "path": "frame_analysis_tuned.txt"},
  {"name": "Video Reconstruction", "path": "describe_tuned.txt"}
]
```

照常运行 `video-analyzer` —— 它会自动使用你优化后的提示词。

## 训练数据格式

### training_data.json

```json
{
  "examples": [
    { "output_dir": "path/to/output" }
  ]
}
```

路径可以是绝对路径，也可以是相对于 `training_data.json` 所在位置的相对路径。

### 需要编辑的文件

| 文件 | 字段 | 是否必填 | 描述 |
|---|---|---|---|
| `analysis.json` | `video_description.response` | 是 | 你理想的最终视频描述 |
| `frame_analyses.json` | `[i].response` | 推荐 | 每帧的理想帧笔记 |
| `analysis.json` | `prompt` | 否 | 保持原样 |
| `transcript.json` | 全部 | 否 | 保持原样 |

## CLI 参考

| 参数 | 默认值 | 描述 |
|---|---|---|
| `--training-data` | 必填 | training_data.json 的路径 |
| `--output-dir` | `tuned_prompts` | 写入优化后提示词文件的目录 |
| `--client` | `ollama` | LLM 客户端：`ollama` 或 `openai_api` |
| `--model` | `llama3.2-vision` | 优化运行使用的视觉模型 |
| `--ollama-url` | `http://localhost:11434` | Ollama 服务器 URL |
| `--api-key` | — | API 密钥（`--client openai_api` 时必填） |
| `--api-url` | — | API 端点 URL（`--client openai_api` 时必填） |
| `--num-candidates` | `10` | 每个模块生成的提示词变体数量。越高越彻底但越慢。范围：5–20 |
| `--num-trials` | `20` | 优化试验次数。越高效果越好但越慢。范围：10–50 |
| `--max-bootstrapped-demos` | `3` | 通过 bootstrapping 生成的最大 few-shot 示例数 |
| `--max-labeled-demos` | `4` | 从你的训练数据中选取的最大 few-shot 示例数 |
| `--description-weight` | `0.7` | 最终描述质量对分数的影响程度（0.0–1.0）。剩余部分权重分配给帧分析质量。如果两者同样重要则使用 `0.5`；如果只想优化最终描述则使用 `1.0` |
| `--log-level` | `INFO` | 日志级别：DEBUG / INFO / WARNING / ERROR |

## LLM 配置

### 使用 Ollama（默认）

```bash
video-analyzer-tune \
  --training-data training_data.json \
  --output-dir tuned_prompts/ \
  --model llama3.2-vision
```

### 使用兼容 OpenAI 的 API（例如 OpenRouter）

```bash
video-analyzer-tune \
  --training-data training_data.json \
  --output-dir tuned_prompts/ \
  --client openai_api \
  --model meta-llama/llama-3.2-11b-vision-instruct \
  --api-url https://openrouter.ai/api/v1 \
  --api-key YOUR_API_KEY
```

## 工作原理

`video-analyzer` 使用两个提示词文件：

1. **`frame_analysis.txt`** —— 每帧调用一次，传入图像和所有之前的帧笔记。生成逐帧观察日志。
2. **`describe.txt`** —— 最后调用一次，传入所有帧笔记和音频转录文本。生成最终视频描述。

`video-analyzer-tune` 将两个提示词包装在一个 DSPy 流水线中，该流水线精确镜像 `video-analyzer` 的处理逻辑。然后运行 [MIPROv2](https://dspy.ai/learn/optimization/optimizers/) —— 一种贝叶斯优化器，生成候选指令变体并根据你的训练示例进行评分。

评分采用 LLM-as-judge 方法：同一模型评估生成输出与理想示例的匹配程度，按 1–5 分制打分。帧笔记质量和最终描述质量通过可配置的 `--description-weight` 进行加权组合。

优化完成后，改进后的指令文本会写入新的 `.txt` 文件，保留所有 `video-analyzer` 用于字符串替换的 `{TOKEN}` 占位符（`{PREVIOUS_FRAMES}`、`{FRAME_NOTES}` 等）—— 使输出文件可以直接替换使用。

## 提升效果的建议

- **使用多个视频。** 即使是 3–5 个多样化的示例也能显著提升优化质量。
- **也编辑帧笔记。** 如果你只编辑最终描述，优化器能获得的好中间分析信号就较少。
- **编辑要具体。** 你的理想示例越清晰地展示你想要的风格和关注点，优化器就能越好地学习。
- **优化和推理使用同一模型。** 优化后的提示词是针对特定模型行为调优的。
- **增加 `--num-candidates` 和 `--num-trials`** 如果时间允许可以获得更好的结果。从默认值开始，再逐步增加。
- **使用 `--description-weight 0.5`** 如果你直接阅读帧笔记，并且同样关心帧笔记和最终描述的质量。

## 开源协议

Apache License 2.0 —— 与 [video-analyzer](https://github.com/byjlw/video-analyzer) 相同。
