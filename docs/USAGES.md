# 视频分析器使用指南

本指南涵盖视频分析器工具的所有配置选项和命令行参数，以及不同用例的实用示例。

## 目录
- [基本用法](#基本用法)
- [命令行参数](#命令行参数)
- [配置系统](#配置系统)
- [常见用例](#常见用例)
- [高级示例](#高级示例)

## 基本用法

### 使用 Ollama 进行本地分析（默认）
```bash
video-analyzer path/to/video.mp4
```

### 使用兼容 OpenAI 的 API（OpenRouter/OpenAI）
```bash
video-analyzer path/to/video.mp4 --client openai_api --api-key your-key --api-url https://openrouter.ai/api/v1
```

## 命令行参数

| 参数 | 描述 | 默认值 | 示例 |
|----------|-------------|---------|---------|
| `video_path` | 输入视频文件的路径 | （必填） | `video.mp4` |
| `--config` | 配置目录的路径 | config/ | `--config /path/to/config/` |
| `--output` | 分析结果的输出目录 | output/ | `--output ./results/` |
| `--client` | 要使用的客户端（ollama 或 openai_api） | ollama | `--client openai_api` |
| `--ollama-url` | Ollama 服务的 URL | http://localhost:11434 | `--ollama-url http://localhost:11434` |
| `--api-key` | 兼容 OpenAI 服务的 API 密钥 | 无 | `--api-key sk-xxx...` |
| `--api-url` | 兼容 OpenAI API 的 API URL | 无 | `--api-url https://openrouter.ai/api/v1` |
| `--model` | 要使用的视觉模型名称 | llama3.2-vision | `--model gpt-4-vision-preview` |
| `--duration` | 要处理的时长（秒） | 无（完整视频） | `--duration 60` |
| `--keep-frames` | 分析后保留提取的帧 | False | `--keep-frames` |
| `--whisper-model` | Whisper 模型大小或模型路径 | medium | `--whisper-model large` |
| `--start-stage` | 开始处理的阶段（1-3） | 1 | `--start-stage 2` |
| `--max-frames` | 要处理的最大帧数。指定后，帧将在整个视频时长中均匀采样，而不是仅取前 N 帧。 | sys.maxsize | `--max-frames 100` |
| `--log-level` | 设置日志级别 | INFO | `--log-level DEBUG` |
| `--prompt` | 关于视频的问题 | "" | `--prompt "What activities are shown?"` |
| `--language` | 设置转录的语言 | 无（自动检测） | `--language en` |
| `--device` | 选择 Whisper 模型的设备 | cpu | `--device cuda` |
| `--temperature` | LLM 生成的温度参数 | 0.2 | `--temperature 0.2` |

### 处理阶段
`--start-stage` 参数允许你从特定阶段开始处理：
1. 帧和音频处理
2. 帧分析
3. 视频重建

## 配置系统

该工具采用级联配置系统，优先级如下：
1. 命令行参数（最高优先级）
2. 用户配置（config/config.json）
3. 默认配置（config/default_config.json）

### 配置文件结构

```json
{
  "clients": {
    "default": "ollama",
    "temperature": 0.2,
    "ollama": {
      "url": "http://localhost:11434",
      "model": "llama3.2-vision"
    },
    "openai_api": {
      "api_key": "",
      "api_url": "https://openrouter.ai/api/v1",
      "model": "meta-llama/llama-3.2-11b-vision-instruct:free"
    }
  },
  "prompt_dir": "",
  "output_dir": "output",
  "frames": {
    "per_minute": 10,
    "analysis_threshold": 10.0,
    "min_difference": 5.0,
    "max_count": 30
  },
  "response_length": {
    "frame": 256,
    "reconstruction": 512,
    "narrative": 1024
  },
  "audio": {
    "sample_rate": 16000,
    "channels": 1,
    "quality_threshold": 0.5,
    "chunk_length": 30,
    "language_confidence_threshold": 0.5,
    "language": null
  },
  "keep_frames": false,
  "prompt": ""
}
```

### 配置选项说明

#### 客户端设置
- `clients.default`: 默认 LLM 客户端（ollama/openai_api）
- `clients.temperature`: LLM 生成的温度参数（0.0-1.0，值越高越具创造性）
- `clients.ollama.url`: Ollama 服务 URL
- `clients.ollama.model`: Ollama 使用的视觉模型
- `clients.openai_api.api_key`: 兼容 OpenAI 服务的 API 密钥
- `clients.openai_api.api_url`: API 端点 URL
- `clients.openai_api.model`: API 服务使用的视觉模型

#### 帧分析设置
- `frames.per_minute`: 每分钟目标提取帧数
- `frames.analysis_threshold`: 关键帧检测阈值
- `frames.min_difference`: 帧之间的最小差异
- `frames.max_count`: 最大提取帧数

#### 响应长度设置
- `response_length.frame`: 帧分析的最大长度
- `response_length.reconstruction`: 视频重建的最大长度
- `response_length.narrative`: 增强叙述的最大长度

#### 音频处理设置
- `audio.sample_rate`: 音频采样率（Hz）
- `audio.channels`: 音频通道数
- `audio.quality_threshold`: 转录的最低质量要求
- `audio.chunk_length`: 音频块处理长度
- `audio.language_confidence_threshold`: 语言检测置信度
- `audio.language`: 强制指定语言（null 表示自动检测）

#### 常规设置
- `prompt_dir`: 自定义提示词目录路径
- `output_dir`: 分析输出目录
- `keep_frames`: 保留提取的帧
- `prompt`: 自定义分析提示词

## 常见用例

### 快速本地分析
```bash
video-analyzer video.mp4
```

### 使用自定义提示词进行高质量云端分析
```bash
video-analyzer video.mp4 \
    --client openai_api \
    --api-key your-key \
    --api-url https://openrouter.ai/api/v1 \
    --model meta-llama/llama-3.2-11b-vision-instruct:free \
    --whisper-model large \
    --prompt "这个视频里发生了什么活动？"
```

### 从帧分析阶段恢复处理
```bash
video-analyzer video.mp4 \
    --start-stage 2 \
    --max-frames 50 \
    --keep-frames
```

### 使用均匀采样帧分析视频
```bash
video-analyzer video.mp4 \
    --max-frames 5 \
    --keep-frames
```
这将在整个视频时长中均匀提取帧。例如，在一个 5 分钟的视频中，它大约每分钟采样一帧，而不是取前 5 帧。

### 指定语言处理
```bash
video-analyzer video.mp4 \
    --language es \
    --whisper-model large
```

### GPU 加速处理
```bash
video-analyzer video.mp4 \
    --device cuda \
    --whisper-model large
```

## 高级示例

### 使用 OpenRouter 的完整配置
```bash
video-analyzer video.mp4 \
    --config custom_config.json \
    --output ./analysis_results \
    --client openai_api \
    --api-key your-key \
    --api-url https://openrouter.ai/api/v1 \
    --model meta-llama/llama-3.2-11b-vision-instruct:free \
    --duration 120 \
    --whisper-model large \
    --keep-frames \
    --log-level DEBUG \
    --prompt "重点关注人物之间的互动"
```

### 带帧数限制的本地处理
```bash
video-analyzer video.mp4 \
    --client ollama \
    --ollama-url http://localhost:11434 \
    --model llama3.2-vision \
    --max-frames 30 \
    --whisper-model medium \
    --device cuda \
    --language en
```

### 从特定阶段恢复分析
```bash
video-analyzer video.mp4 \
    --start-stage 2 \
    --output ./custom_output \
    --keep-frames \
    --max-frames 50 \
    --prompt "描述主要事件"
```

### 使用本地 Whisper 模型
```bash
video-analyzer video.mp4 \
    --whisper-model /path/to/whisper/model \
    --device cuda \
    --start-stage 1
```
