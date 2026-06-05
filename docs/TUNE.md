# Video Analyzer Tune 使用指南

本文档详细介绍如何使用 `video-analyzer-tune` 子包自动优化视频分析的提示词，使其更适配你的特定内容类型和使用场景。

## 目录

- [概述](#概述)
- [工作原理](#工作原理)
- [前置要求](#前置要求)
- [安装](#安装)
- [使用流程](#使用流程)
- [训练数据格式](#训练数据格式)
- [命令行参数](#命令行参数)
- [模型配置示例](#模型配置示例)
- [内部架构](#内部架构)
- [最佳实践](#最佳实践)
- [常见问题](#常见问题)

---

## 概述

`video-analyzer` 通过两个提示词驱动视频分析：

| 提示词 | 作用 | 阶段 |
|---|---|---|
| 帧分析提示词 | 逐帧分析视频画面，记录视觉观察 | Stage 2 |
| 视频重建提示词 | 综合所有帧笔记和音频转录，生成连贯描述 | Stage 3 |

这两个提示词是通用模板，适用于大多数视频。但如果你需要分析**特定类型**的内容（如编程教程、体育赛事、监控录像、产品评测），通用提示词可能无法精准捕捉你关心的细节。

`video-analyzer-tune` 使用 **DSPy MIPROv2** 贝叶斯优化器，基于你提供的"理想输出示例"，自动找到更适合你场景的提示词指令。优化后的提示词写入新文件，通过配置指向即可使用，主包代码完全不受影响。

---

## 工作原理

### 核心思路

1. **你提供理想输出** —— 在 `video-analyzer` 的分析结果上，手动编辑你期望得到的理想描述
2. **优化器学习规律** —— MIPROv2 分析"输入 → 理想输出"的对应关系，生成多种提示词变体
3. **评分筛选最优** —— 用 LLM-as-judge 评估每种变体的效果，贝叶斯优化找到最佳组合
4. **输出新提示词** —— 将优化后的指令写入 `.txt` 文件，保留所有 `{TOKEN}` 占位符，直接替换使用

### MIPROv2 优化流程

```
训练数据（理想输出）
       │
       ▼
┌─────────────────┐
│  生成候选提示词  │  ← 基于训练数据生成 N 个提示词变体
│  (--num-candidates)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   贝叶斯优化    │  ← 在验证集上测试，迭代寻找最佳组合
│  (--num-trials) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  输出优化提示词  │  ← 写入 tuned_prompts/ 目录
└─────────────────┘
```

---

## 前置要求

- Python 3.8+
- `video-analyzer >= 0.1.2`（已安装）
- FFmpeg（video-analyzer 所需）
- Ollama（本地模式）或 OpenAI 兼容 API 密钥（云端模式）

---

## 安装

```bash
pip install video-analyzer-tune
```

或从源码安装：

```bash
cd video-analyzer-tune
pip install -e .
```

---

## 使用流程

### 第一步：生成分析输出并保留帧

在代表性视频上运行 `video-analyzer`，**必须**添加 `--keep-frames`：

```bash
video-analyzer my_video.mp4 --keep-frames
```

输出目录结构：
```
output/
├── analysis.json       # 分析结果
└── frames/             # 提取的关键帧图片（优化器需要读取）
    ├── frame_0000.jpg
    ├── frame_0001.jpg
    └── ...
```

### 第二步：编辑 analysis.json，填写理想输出

打开 `output/analysis.json`，编辑以下字段：

#### 必填：最终视频描述

编辑 `video_description.response`，写上你认为最理想的最终描述：

```json
{
  "video_description": {
    "response": "本视频演示了如何在 VS Code 中配置 Python 调试环境。开发者首先打开 settings.json，然后添加 python.analysis.typeChecking 配置项，最后运行调试器验证配置生效。"
  }
}
```

#### 推荐：逐帧理想笔记

编辑每个 `frame_analyses[i].response`，帮助优化器理解中间分析应该关注什么：

```json
{
  "frame_analyses": [
    {
      "frame": 0,
      "timestamp": 0.0,
      "response": "画面显示 VS Code 欢迎页，左侧 Explorer 面板可见项目结构"
    },
    {
      "frame": 1,
      "timestamp": 4.5,
      "response": "开发者按下 Ctrl+Shift+P 打开命令面板，输入 'settings json'"
    }
  ]
}
```

**编辑原则：**
- 描述你**真正想要**的风格、长度和关注点
- 教程类视频：理想描述应包含步骤总结和技术细节
- 监控类视频：理想描述应关注异常行为和关键事件
- 评测类视频：理想描述应覆盖产品特性和使用体验

### 第三步：创建 training_data.json

单视频示例：

```json
{
  "examples": [
    { "output_dir": "output" }
  ]
}
```

多视频示例（效果更好）：

```json
{
  "examples": [
    { "output_dir": "output/tutorial_1" },
    { "output_dir": "output/tutorial_2" },
    { "output_dir": "output/review_1" }
  ]
}
```

**路径规则：**
- 相对路径：相对于 `training_data.json` 所在目录
- 绝对路径：直接使用绝对路径
- 每个 `output_dir` 必须包含 `analysis.json` 和 `frames/` 目录

### 第四步：运行优化器

**Ollama 本地模式：**

```bash
video-analyzer-tune \
  --training-data training_data.json \
  --output-dir tuned_prompts/ \
  --model llama3.2-vision
```

**OpenRouter 云端模式：**

```bash
video-analyzer-tune \
  --training-data training_data.json \
  --output-dir tuned_prompts/ \
  --client openai_api \
  --model meta-llama/llama-3.2-11b-vision-instruct \
  --api-url https://openrouter.ai/api/v1 \
  --api-key YOUR_API_KEY
```

**典型输出：**

```
Loaded 3 training example(s)
  Example 1: 28 frames, with ideal frame notes
  Example 2: 15 frames, without ideal frame notes
  Example 3: 22 frames, with ideal frame notes

Starting optimization: 2 train / 1 val examples, 10 candidates, 20 trials
Evaluating baseline (unoptimized) prompts...
Baseline score: 42.3%

Evaluating optimized prompts...
Optimized score: 71.8%
Improvement: +29.5%

Tuning complete! Add the following to your config/config.json:

  "prompt_dir": "tuned_prompts",
  "prompts": [
    {"name": "Frame Analysis", "path": "frame_analysis_tuned.txt"},
    {"name": "Video Reconstruction", "path": "describe_tuned.txt"}
  ]
```

### 第五步：更新配置使用优化提示词

将优化器输出的配置片段添加到 `config/config.json`：

```json
{
  "clients": { ... },
  "prompt_dir": "tuned_prompts",
  "prompts": [
    {"name": "Frame Analysis", "path": "frame_analysis_tuned.txt"},
    {"name": "Video Reconstruction", "path": "describe_tuned.txt"}
  ],
  ...
}
```

然后照常运行 `video-analyzer`，它会自动加载优化后的提示词：

```bash
video-analyzer new_video.mp4
```

---

## 训练数据格式

### training_data.json

```json
{
  "examples": [
    { "output_dir": "path/to/output" }
  ]
}
```

### analysis.json 中需要编辑的字段

| 字段 | 是否必填 | 描述 |
|---|---|---|
| `video_description.response` | **是** | 理想的最终视频描述 |
| `frame_analyses[i].response` | 推荐 | 每帧的理想分析笔记 |
| `prompt` | 否 | 保持原样（用户的原始问题） |
| `transcript` | 否 | 保持原样（音频转录结果） |

### 路径解析规则

`training_data.json` 支持三种传入方式：

| 传入方式 | 示例 | 说明 |
|---|---|---|
| 目录路径 | `output/` | 目录必须包含 `analysis.json` 和 `frames/` |
| 直接指向 analysis.json | `output/analysis.json` | 会自动使用其父目录 |
| training_data.json 包装器 | `training_data.json` | 包含多个 `examples` 条目 |

---

## 命令行参数

| 参数 | 默认值 | 描述 |
|---|---|---|
| `--training-data` | **必填** | `training_data.json` 的路径，或单个 `output/` 目录，或 `analysis.json` 文件 |
| `--output-dir` | `tuned_prompts` | 优化后提示词文件的输出目录 |
| `--client` | `ollama` | LLM 客户端：`ollama` 或 `openai_api`。如果提供 `--api-key` 但未指定 `--client`，自动推断为 `openai_api` |
| `--model` | `llama3.2-vision` | 优化运行使用的视觉模型 |
| `--ollama-url` | `http://localhost:11434` | Ollama 服务 URL |
| `--api-key` | — | API 密钥（`--client openai_api` 时必填） |
| `--api-url` | — | API 端点 URL（`--client openai_api` 时必填） |
| `--num-candidates` | `10` | 每个模块生成的提示词变体数量。越高搜索越彻底但越慢。建议范围：5–20 |
| `--num-trials` | `20` | 贝叶斯优化试验次数。越高效果越好但越慢。建议范围：10–50 |
| `--max-bootstrapped-demos` | `3` | 通过 bootstrapping 自动生成的 few-shot 示例数 |
| `--max-labeled-demos` | `4` | 从训练数据中直接抽取的 few-shot 示例数 |
| `--description-weight` | `0.7` | 最终描述质量占总分的权重（0.0–1.0）。剩余权重分配给帧笔记质量。如果两者同样重要用 `0.5`；如果只关心最终描述用 `1.0` |
| `--log-level` | `INFO` | 日志级别：`DEBUG` / `INFO` / `WARNING` / `ERROR` |

### 参数调优建议

| 场景 | `--num-candidates` | `--num-trials` | `--description-weight` |
|---|---|---|---|
| 快速尝试 | 5 | 10 | 0.7 |
| 默认配置 | 10 | 20 | 0.7 |
| 追求最佳效果 | 15 | 40 | 按需调整 |
| 关注帧笔记质量 | 10 | 20 | 0.5 |
| 只看最终描述 | 10 | 20 | 1.0 |

---

## 模型配置示例

### Ollama 本地优化

```bash
video-analyzer-tune \
  --training-data training_data.json \
  --output-dir tuned_prompts/ \
  --model llama3.2-vision \
  --ollama-url http://localhost:11434
```

### OpenRouter 云端优化

```bash
video-analyzer-tune \
  --training-data training_data.json \
  --output-dir tuned_prompts/ \
  --client openai_api \
  --model meta-llama/llama-3.2-11b-vision-instruct \
  --api-url https://openrouter.ai/api/v1 \
  --api-key YOUR_API_KEY
```

### OpenAI 官方 API

```bash
video-analyzer-tune \
  --training-data training_data.json \
  --output-dir tuned_prompts/ \
  --client openai_api \
  --model gpt-4o \
  --api-url https://api.openai.com/v1 \
  --api-key YOUR_API_KEY
```

---

## 内部架构

| 模块 | 文件 | 职责 |
|---|---|---|
| 数据加载 | `training_data.py` | 加载和验证训练数据。支持目录、`analysis.json` 文件、`training_data.json` 三种传入方式。验证必填字段 |
| 签名定义 | `signatures.py` | 定义 4 个 DSPy Signature：帧分析、视频重建、描述评分、帧笔记评分 |
| 流水线 | `pipeline.py` | DSPy 流水线，**精确镜像** `video-analyzer` 的两阶段逻辑：逐帧分析（累积上下文）→ 最终重建。保证优化后的提示词可直接替换 |
| 评分器 | `metrics.py` | LLM-as-judge 评分机制。对比候选输出与理想输出，按 1–5 分制打分。最多采样 5 帧评估以加速 |
| 优化器 | `tuner.py` | 编排 MIPROv2 优化：配置 LM → 构建示例 → 80/20 划分训练/验证集 → 评估基线 → 运行优化 → 评估改进 |
| 输出写入 | `prompt_writer.py` | 从优化后的 DSPy 模块提取指令文本，写入 `.txt` 文件，保留所有 `{TOKEN}` 占位符 |

---

## 最佳实践

### 1. 训练数据数量

- **至少 1 个视频**：可以运行，但效果有限
- **3–5 个视频**：显著提升优化质量
- **5 个以上**：边际收益递减，但多样性更高

### 2. 内容多样性

尽量覆盖你关心的不同场景：

```json
{
  "examples": [
    { "output_dir": "output/tutorial_beginner" },
    { "output_dir": "output/tutorial_advanced" },
    { "output_dir": "output/troubleshooting" },
    { "output_dir": "output/quick_tip" }
  ]
}
```

### 3. 编辑质量

- **具体明确**：避免模糊的"很好""不错"，要写清具体包含哪些信息
- **保持一致风格**：所有示例的最终描述应保持相似的风格和结构
- **覆盖边界情况**：如果有特殊场景（如无音频、夜间画面），提供对应示例

### 4. 模型一致性

- **优化和推理使用同一模型**：提示词是针对特定模型的行为模式优化的
- 如果用 Ollama 优化，推理也用 Ollama；如果用 OpenRouter 优化，推理也用相同模型

### 5. 迭代优化

第一次优化后，用新提示词分析更多视频，继续编辑不理想的结果，再次运行优化：

```
第1轮：用 3 个示例优化 → 得到提示词 V1
     ↓
用 V1 分析新视频 → 编辑不理想的结果
     ↓
第2轮：加入新示例，共 5 个 → 得到提示词 V2
```

---

## 常见问题

**Q: 为什么必须手动编辑 analysis.json？**

A: 优化器需要知道"好结果长什么样"。你不编辑，它就不知道优化目标是什么，无法判断哪种提示词变体更好。

**Q: 优化一次需要多长时间？**

A: 取决于 `--num-candidates` 和 `--num-trials`：
- Ollama 本地：默认配置（10/20）通常需要 30 分钟到 2 小时
- OpenRouter API：默认配置通常需要 10–30 分钟（并行调用）
- 如果用更大的模型（如 GPT-4o），每次评分更慢

**Q: 可以只编辑最终描述，不编辑帧笔记吗？**

A: 可以，但效果会打折扣。设置 `--description-weight 1.0` 让优化器只关注最终描述。推荐至少编辑关键帧的笔记。

**Q: 优化后的提示词能跨模型使用吗？**

A: 可以运行，但效果可能下降。提示词是针对特定模型的行为模式（如输出风格、遵循指令的方式）优化的。

**Q: 提示词文件里的 `{TOKEN}` 是什么？**

A: 占位符，`video-analyzer` 运行时会替换为实际内容：
- `{PREVIOUS_FRAMES}` → 之前帧的分析笔记
- `{FRAME_NOTES}` → 所有帧的分析笔记
- `{TRANSCRIPT}` → 音频转录文本
- `{FIRST_FRAME}` → 第一帧的分析笔记
- `{prompt}` → 用户的问题

**Q: 优化完成后可以删除训练数据吗？**

A: 可以。优化过程需要 `frames/` 中的图片来评估，但完成后只需要 `tuned_prompts/` 目录中的 `.txt` 文件。

**Q: 如何恢复到默认提示词？**

A: 从 `config/config.json` 中移除 `prompt_dir` 和 `prompts` 字段，或将其指向空值。`video-analyzer` 会自动回退到包内默认提示词。
