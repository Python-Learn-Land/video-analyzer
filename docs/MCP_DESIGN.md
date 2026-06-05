# Video Analyzer MCP 服务器设计文档

本文档描述如何将 `video-analyzer` 封装为 [Model Context Protocol (MCP)](https://modelcontextprotocol.io) 服务器，使 AI Agent 能够通过标准化接口调用视频分析能力。

## 目录

- [为什么需要 MCP 封装](#为什么需要-mcp-封装)
- [架构设计](#架构设计)
- [MCP 能力映射](#mcp-能力映射)
- [实现方案对比](#实现方案对比)
- [核心工具设计](#核心工具设计)
- [资源与提示设计](#资源与提示设计)
- [代码实现](#代码实现)
- [部署与运行](#部署与运行)
- [分享给他人使用](#分享给他人使用)
- [客户端配置示例](#客户端配置示例)
- [注意事项与最佳实践](#注意事项与最佳实践)

---

## 为什么需要 MCP 封装

`video-analyzer` 是一个强大的视频理解工具，但 CLI 接口对 AI Agent 不够友好。通过 MCP 封装后，Agent 可以：

- **理解视频内容** —— 分析屏幕录像、监控片段、教学视频、会议录屏等
- **无需关心底层实现** —— 不用处理 FFmpeg、Whisper、Ollama 等依赖
- **统一调用方式** —— 通过 MCP 标准协议，任何支持 MCP 的 Agent 都能使用
- **获取结构化输出** —— 直接获得 JSON 分析结果，便于后续处理

**典型使用场景：**
- 让 Agent 分析用户上传的视频并回答相关问题
- 批量处理视频内容，提取关键信息
- 结合视频分析和代码审查，理解演示视频中的操作步骤

---

## 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                        AI Agent (Claude/Cursor/Cline)            │
│                                                                  │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐ │
│  │ analyze_video   │    │ get_video_info  │    │ get_result  │ │
│  │ (提交分析任务)   │    │ (获取视频信息)   │    │ (查询结果)   │ │
│  └────────┬────────┘    └────────┬────────┘    └──────┬──────┘ │
│           │                      │                     │        │
│           └──────────────────────┼─────────────────────┘        │
│                                  ▼                              │
│                    ┌─────────────────────────┐                  │
│                    │     MCP Protocol        │                  │
│                    │  (stdio / SSE / HTTP)   │                  │
│                    └───────────┬─────────────┘                  │
│                                │                                │
└────────────────────────────────┼────────────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   video-analyzer-mcp    │
                    │      (MCP Server)       │
                    │                         │
                    │  ┌───────────────────┐  │
                    │  │   Task Manager    │  │
                    │  │  (任务队列/状态)   │  │
                    │  └───────────────────┘  │
                    │  ┌───────────────────┐  │
                    │  │  Video Analyzer   │  │
                    │  │   (核心分析引擎)   │  │
                    │  └───────────────────┘  │
                    │  ┌───────────────────┐  │
                    │  │  Result Storage   │  │
                    │  │   (结果存储)       │  │
                    │  └───────────────────┘  │
                    └───────────┬─────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
        ┌─────▼─────┐    ┌─────▼─────┐    ┌─────▼─────┐
        │   Ollama  │    │  Whisper  │    │   FFmpeg  │
        │  (视觉LLM) │    │ (音频转录) │    │ (视频处理) │
        └───────────┘    └───────────┘    └───────────┘
```

---

## MCP 能力映射

| video-analyzer 能力 | MCP 原语 | 说明 |
|---|---|---|
| 提交视频分析任务 | `Tool: analyze_video` | Agent 调用，异步返回 task_id |
| 查询任务状态/结果 | `Tool: get_task_status` | Agent 轮询使用 |
| 获取视频元信息 | `Tool: get_video_info` | 不调用 LLM，瞬间返回 |
| 列出历史分析任务 | `Tool: list_tasks` | 查看所有任务状态 |
| 读取分析结果文件 | `Resource: analysis://{task_id}` | 以 Resource 形式暴露结果 |
| 视频分析提示词模板 | `Prompt: video-analysis` | 引导 Agent 如何提问 |

---

## 实现方案对比

### 方案一：异步任务模式（推荐）

适用于生产环境，支持任意长度视频。

```
Agent → analyze_video(video_path) → {task_id, status: "pending"}
Agent → get_task_status(task_id)  → {status: "processing", progress: 60}
Agent → get_task_status(task_id)  → {status: "completed", result: {...}}
```

**优点：**
- 不超时，支持长视频分析
- Agent 可以在等待期间执行其他操作
- 任务可持久化，支持断点续传

**缺点：**
- 需要轮询机制
- 实现复杂度较高

### 方案二：同步快捷模式

适用于短视频（30 秒内），一步返回结果。

```
Agent → analyze_video_short(video_path, duration=30) → "视频描述文本..."
```

**优点：**
- 实现简单，Agent 一步拿到结果
- 适合快速问答场景

**缺点：**
- 容易超时（MCP 工具调用通常有 60-300 秒超时）
- 不适合长视频

### 方案三：混合模式（推荐实现）

同时提供异步和同步工具，Agent 根据场景自选。

| 工具 | 适用场景 | 超时风险 |
|---|---|---|
| `analyze_video` | 长视频、重要分析 | 无（异步） |
| `analyze_video_quick` | 短视频、快速预览 | 有（同步，限 60 秒） |
| `get_video_info` | 任何视频 | 无（瞬间返回） |

---

## 核心工具设计

### Tool: `analyze_video`

提交异步视频分析任务。

```json
{
  "name": "analyze_video",
  "description": "提交视频分析任务。对于长视频，使用此工具提交后，通过 get_task_status 轮询结果。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "video_path": {
        "type": "string",
        "description": "视频文件的绝对路径"
      },
      "prompt": {
        "type": "string",
        "description": "关于视频的问题，例如'视频中展示了什么活动？'"
      },
      "duration": {
        "type": "number",
        "description": "只分析前 N 秒，不指定则分析完整视频"
      },
      "max_frames": {
        "type": "integer",
        "description": "最大提取帧数，默认 30"
      },
      "language": {
        "type": "string",
        "description": "音频语言代码，如 'zh', 'en'。不指定则自动检测"
      }
    },
    "required": ["video_path"]
  }
}
```

**返回示例：**
```json
{
  "task_id": "va_20240605_143022_a1b2c3",
  "status": "pending",
  "message": "视频分析任务已提交，预计耗时 2-5 分钟",
  "estimated_duration": "2-5 min"
}
```

---

### Tool: `analyze_video_quick`

同步分析短视频（限 60 秒内）。

```json
{
  "name": "analyze_video_quick",
  "description": "快速分析短视频（60秒以内），同步返回结果。如果视频较长，会自动截取前60秒。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "video_path": {
        "type": "string",
        "description": "视频文件的绝对路径"
      },
      "prompt": {
        "type": "string",
        "description": "关于视频的问题"
      },
      "max_frames": {
        "type": "integer",
        "description": "最大提取帧数，默认 5"
      }
    },
    "required": ["video_path"]
  }
}
```

**返回示例：**
```json
{
  "description": "视频展示了一位开发者在 VS Code 中编写 Python 代码...",
  "transcript": "今天我们来讲解如何实现一个 MCP 服务器...",
  "frames_analyzed": 5,
  "duration_processed": 60
}
```

---

### Tool: `get_task_status`

查询异步任务状态。

```json
{
  "name": "get_task_status",
  "description": "查询视频分析任务的状态和结果",
  "inputSchema": {
    "type": "object",
    "properties": {
      "task_id": {
        "type": "string",
        "description": "任务 ID"
      }
    },
    "required": ["task_id"]
  }
}
```

**返回示例（处理中）：**
```json
{
  "task_id": "va_20240605_143022_a1b2c3",
  "status": "processing",
  "progress": 60,
  "stage": "frame_analysis",
  "message": "正在分析第 18/30 帧"
}
```

**返回示例（已完成）：**
```json
{
  "task_id": "va_20240605_143022_a1b2c3",
  "status": "completed",
  "result": {
    "description": "视频展示了一位开发者...",
    "transcript": "今天我们来讲解...",
    "frame_count": 30,
    "output_path": "/tmp/video-analyzer-mcp/va_20240605_143022_a1b2c3/analysis.json"
  }
}
```

---

### Tool: `get_video_info`

获取视频基本信息（不调用 LLM）。

```json
{
  "name": "get_video_info",
  "description": "获取视频文件的基本信息：时长、分辨率、帧率、是否有音频等。不调用 AI，瞬间返回。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "video_path": {
        "type": "string",
        "description": "视频文件的绝对路径"
      }
    },
    "required": ["video_path"]
  }
}
```

**返回示例：**
```json
{
  "duration": 245.5,
  "width": 1920,
  "height": 1080,
  "fps": 30,
  "has_audio": true,
  "format": "mp4",
  "file_size_mb": 156.3
}
```

---

### Tool: `list_tasks`

列出最近的分析任务。

```json
{
  "name": "list_tasks",
  "description": "列出最近的视频分析任务及其状态",
  "inputSchema": {
    "type": "object",
    "properties": {
      "limit": {
        "type": "integer",
        "description": "返回任务数量上限，默认 10"
      }
    }
  }
}
```

---

## 资源与提示设计

### Resource: `analysis://{task_id}`

以 Resource 形式暴露分析结果，Agent 可以通过 MCP Resource 接口读取。

```
URI: analysis://va_20240605_143022_a1b2c3
MIME type: application/json
```

内容即 `analysis.json` 的完整内容。

### Prompt: `video-analysis`

引导 Agent 如何有效地使用视频分析工具。

```
当你需要理解视频内容时：

1. 首先使用 get_video_info 了解视频基本信息
2. 如果视频超过 60 秒，使用 analyze_video 提交异步任务
3. 如果视频较短，可直接使用 analyze_video_quick
4. 提交异步任务后，等待 30 秒再查询状态
5. 分析完成后，向用户总结视频的关键内容

提问建议：
- "视频中展示了什么活动？"
- "请总结视频的主要内容"
- "视频中的人物在做什么？"
- "视频的技术演示步骤是什么？"
```

---

## 代码实现

### 项目结构

```
video-analyzer-mcp/
├── pyproject.toml
├── README.md
├── requirements.txt
└── video_analyzer_mcp/
    ├── __init__.py
    ├── server.py          # MCP 服务器主入口
    ├── task_manager.py    # 任务队列与状态管理
    ├── tools.py           # MCP Tool 实现
    ├── resources.py       # MCP Resource 实现
    └── prompts.py         # MCP Prompt 定义
```

### 核心代码：server.py

```python
#!/usr/bin/env python3
"""Video Analyzer MCP Server"""

import asyncio
import json
import logging
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
    Resource,
    Prompt,
    PromptMessage,
    GetPromptResult,
)

from video_analyzer.config import Config
from video_analyzer.cli import create_client, cleanup_files
from video_analyzer.frame import VideoProcessor
from video_analyzer.prompt import PromptLoader
from video_analyzer.analyzer import VideoAnalyzer
from video_analyzer.audio_processor import AudioProcessor

logger = logging.getLogger(__name__)

# 任务存储（生产环境应使用 Redis/数据库）
tasks = {}

server = Server("video-analyzer-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="analyze_video",
            description="提交视频分析任务（异步）。适用于长视频。返回 task_id，后续用 get_task_status 查询结果。",
            inputSchema={
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "视频文件的绝对路径"},
                    "prompt": {"type": "string", "description": "关于视频的问题"},
                    "duration": {"type": "number", "description": "只分析前 N 秒"},
                    "max_frames": {"type": "integer", "description": "最大提取帧数，默认 30"},
                    "language": {"type": "string", "description": "音频语言代码，如 'zh', 'en'"},
                },
                "required": ["video_path"],
            },
        ),
        Tool(
            name="analyze_video_quick",
            description="快速分析短视频（60秒以内），同步返回结果。",
            inputSchema={
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "视频文件的绝对路径"},
                    "prompt": {"type": "string", "description": "关于视频的问题"},
                    "max_frames": {"type": "integer", "description": "最大提取帧数，默认 5"},
                },
                "required": ["video_path"],
            },
        ),
        Tool(
            name="get_task_status",
            description="查询视频分析任务的状态和结果。",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务 ID"},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="get_video_info",
            description="获取视频文件的基本信息（时长、分辨率等），不调用 AI。",
            inputSchema={
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "视频文件的绝对路径"},
                },
                "required": ["video_path"],
            },
        ),
        Tool(
            name="list_tasks",
            description="列出最近的视频分析任务。",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "返回数量上限，默认 10"},
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    if name == "analyze_video":
        return await handle_analyze_video(arguments)
    elif name == "analyze_video_quick":
        return await handle_analyze_video_quick(arguments)
    elif name == "get_task_status":
        return await handle_get_task_status(arguments)
    elif name == "get_video_info":
        return await handle_get_video_info(arguments)
    elif name == "list_tasks":
        return await handle_list_tasks(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")


async def handle_analyze_video(args: dict) -> list[TextContent]:
    """Submit async video analysis task."""
    video_path = Path(args["video_path"])
    if not video_path.exists():
        return [TextContent(type="text", text=f"错误：视频文件不存在: {video_path}")]

    task_id = f"va_{uuid.uuid4().hex[:12]}"
    output_dir = Path(f"/tmp/video-analyzer-mcp/{task_id}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 保存任务信息
    tasks[task_id] = {
        "id": task_id,
        "status": "pending",
        "progress": 0,
        "stage": "initialized",
        "video_path": str(video_path),
        "output_dir": str(output_dir),
        "created_at": asyncio.get_event_loop().time(),
        "result": None,
    }

    # 在后台启动分析任务
    asyncio.create_task(run_analysis(task_id, args))

    return [TextContent(
        type="text",
        text=json.dumps({
            "task_id": task_id,
            "status": "pending",
            "message": f"视频分析任务已提交。任务 ID: {task_id}",
            "hint": "使用 get_task_status 工具查询进度，建议等待 30 秒后再查询。",
        }, ensure_ascii=False, indent=2)
    )]


async def run_analysis(task_id: str, args: dict):
    """Run video analysis in background."""
    task = tasks[task_id]
    task["status"] = "processing"
    task["stage"] = "extracting"
    task["progress"] = 10

    try:
        # 使用 video-analyzer 的核心逻辑进行分析
        # 这里复用 video_analyzer 包内部的类，而非调用 CLI
        config = Config("config")
        video_path = Path(args["video_path"])
        output_dir = Path(task["output_dir"])

        # 覆盖配置
        if args.get("duration"):
            config.config["duration"] = args["duration"]
        if args.get("max_frames"):
            config.config["frames"]["max_count"] = args["max_frames"]
        if args.get("language"):
            config.config["audio"]["language"] = args["language"]
        if args.get("prompt"):
            config.config["prompt"] = args["prompt"]

        # Stage 1: 帧和音频提取
        task["stage"] = "frame_audio_extraction"
        task["progress"] = 20

        audio_processor = AudioProcessor(
            language=config.get("audio", {}).get("language", ""),
            model_size_or_path=config.get("audio", {}).get("whisper_model", "medium"),
            device=config.get("audio", {}).get("device", "cpu"),
        )

        try:
            audio_path = audio_processor.extract_audio(video_path, output_dir)
            transcript = audio_processor.transcribe(audio_path) if audio_path else None
        except Exception as e:
            logger.warning(f"Audio processing failed: {e}")
            transcript = None

        processor = VideoProcessor(video_path, output_dir / "frames", config.get("clients", {}).get("default", "ollama"))
        frames = processor.extract_keyframes(
            frames_per_minute=config.get("frames", {}).get("per_minute", 60),
            duration=config.get("duration"),
            max_frames=args.get("max_frames", sys.maxsize),
        )

        # Stage 2: 帧分析
        task["stage"] = "frame_analysis"
        task["progress"] = 50

        client = create_client(config)
        model = config.get("clients", {}).get(config.get("clients", {}).get("default", "ollama"), {}).get("model", "llama3.2-vision")
        prompt_loader = PromptLoader(config.get("prompt_dir"), config.get("prompts", []))

        analyzer = VideoAnalyzer(
            client, model, prompt_loader,
            config.get("clients", {}).get("temperature", 0.2),
            config.get("prompt", ""),
        )

        frame_analyses = []
        total_frames = len(frames)
        for i, frame in enumerate(frames):
            analysis = analyzer.analyze_frame(frame)
            frame_analyses.append(analysis)
            task["progress"] = 50 + int((i + 1) / total_frames * 40)

        # Stage 3: 视频重建
        task["stage"] = "video_reconstruction"
        task["progress"] = 95

        video_description = analyzer.reconstruct_video(frame_analyses, frames, transcript)

        # 保存结果
        results = {
            "metadata": {
                "model": model,
                "frames_extracted": len(frames),
                "duration_processed": config.get("duration"),
            },
            "transcript": {
                "text": transcript.text if transcript else None,
            } if transcript else None,
            "frame_analyses": frame_analyses,
            "video_description": video_description,
        }

        with open(output_dir / "analysis.json", "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        task["status"] = "completed"
        task["progress"] = 100
        task["result"] = results
        task["stage"] = "completed"

        # 清理临时文件
        if not config.get("keep_frames"):
            cleanup_files(output_dir)

    except Exception as e:
        logger.error(f"Analysis failed for task {task_id}: {e}")
        task["status"] = "failed"
        task["stage"] = "error"
        task["result"] = {"error": str(e)}


async def handle_analyze_video_quick(args: dict) -> list[TextContent]:
    """Quick sync analysis for short videos."""
    # 强制限制时长为 60 秒
    args["duration"] = min(args.get("duration", 60), 60)
    args["max_frames"] = min(args.get("max_frames", 5), 10)

    # 复用异步逻辑，但等待完成
    task_id = f"va_{uuid.uuid4().hex[:12]}"
    output_dir = Path(f"/tmp/video-analyzer-mcp/{task_id}")
    output_dir.mkdir(parents=True, exist_ok=True)

    tasks[task_id] = {
        "id": task_id,
        "status": "processing",
        "video_path": args["video_path"],
        "output_dir": str(output_dir),
    }

    await run_analysis(task_id, args)

    task = tasks[task_id]
    if task["status"] == "completed":
        desc = task["result"]["video_description"]["response"]
        transcript_text = task["result"]["transcript"]["text"] if task["result"]["transcript"] else None
        return [TextContent(
            type="text",
            text=json.dumps({
                "description": desc,
                "transcript": transcript_text,
                "frames_analyzed": len(task["result"]["frame_analyses"]),
                "task_id": task_id,
            }, ensure_ascii=False, indent=2)
        )]
    else:
        return [TextContent(type="text", text=f"分析失败: {task['result'].get('error', '未知错误')}")]


async def handle_get_task_status(args: dict) -> list[TextContent]:
    """Get task status."""
    task_id = args["task_id"]
    if task_id not in tasks:
        return [TextContent(type="text", text=f"错误：任务不存在: {task_id}")]

    task = tasks[task_id]
    response = {
        "task_id": task_id,
        "status": task["status"],
        "progress": task["progress"],
        "stage": task["stage"],
    }

    if task["status"] == "completed":
        response["result"] = {
            "description": task["result"]["video_description"]["response"],
            "transcript": task["result"]["transcript"]["text"] if task["result"]["transcript"] else None,
            "frames_analyzed": len(task["result"]["frame_analyses"]),
        }
    elif task["status"] == "failed":
        response["error"] = task["result"].get("error", "未知错误")

    return [TextContent(type="text", text=json.dumps(response, ensure_ascii=False, indent=2))]


async def handle_get_video_info(args: dict) -> list[TextContent]:
    """Get video metadata using ffprobe."""
    video_path = Path(args["video_path"])
    if not video_path.exists():
        return [TextContent(type="text", text=f"错误：视频文件不存在: {video_path}")]

    try:
        # 使用 ffprobe 获取视频信息
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        data = json.loads(result.stdout)

        video_stream = next((s for s in data["streams"] if s["codec_type"] == "video"), {})
        audio_stream = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)

        info = {
            "duration": float(data["format"].get("duration", 0)),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "fps": eval(video_stream.get("r_frame_rate", "0/1")),  # e.g. "30/1" -> 30
            "has_audio": audio_stream is not None,
            "format": data["format"].get("format_name", "").split(",")[0],
            "file_size_mb": round(float(data["format"].get("size", 0)) / 1024 / 1024, 2),
        }
        return [TextContent(type="text", text=json.dumps(info, ensure_ascii=False, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=f"获取视频信息失败: {e}")]


async def handle_list_tasks(args: dict) -> list[TextContent]:
    """List recent tasks."""
    limit = args.get("limit", 10)
    task_list = [
        {
            "task_id": tid,
            "status": t["status"],
            "stage": t["stage"],
            "progress": t["progress"],
            "video_path": t["video_path"],
        }
        for tid, t in sorted(tasks.items(), key=lambda x: x[1].get("created_at", 0), reverse=True)
    ][:limit]

    return [TextContent(type="text", text=json.dumps(task_list, ensure_ascii=False, indent=2))]


@server.list_resources()
async def list_resources() -> list[Resource]:
    """List available resources."""
    resources = []
    for task_id, task in tasks.items():
        if task["status"] == "completed":
            resources.append(Resource(
                uri=f"analysis://{task_id}",
                name=f"分析结果: {task_id}",
                mimeType="application/json",
                description=f"视频分析任务的完整结果: {task['video_path']}",
            ))
    return resources


@server.read_resource()
async def read_resource(uri: str) -> str:
    """Read resource content."""
    if uri.startswith("analysis://"):
        task_id = uri.replace("analysis://", "")
        if task_id in tasks and tasks[task_id]["status"] == "completed":
            output_dir = Path(tasks[task_id]["output_dir"])
            analysis_file = output_dir / "analysis.json"
            if analysis_file.exists():
                return analysis_file.read_text()
    raise ValueError(f"Resource not found: {uri}")


@server.list_prompts()
async def list_prompts() -> list[Prompt]:
    """List available prompts."""
    return [
        Prompt(
            name="video-analysis",
            description="指导 Agent 如何有效使用视频分析工具的提示词",
        ),
    ]


@server.get_prompt()
async def get_prompt(name: str, arguments: dict | None = None) -> GetPromptResult:
    """Get prompt content."""
    if name == "video-analysis":
        return GetPromptResult(
            description="视频分析工具使用指南",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text="""当你需要理解视频内容时，请遵循以下步骤：

1. **获取视频信息**：首先使用 `get_video_info` 了解视频时长、分辨率等基本信息
2. **选择分析方式**：
   - 如果视频 ≤ 60 秒，使用 `analyze_video_quick` 同步获取结果
   - 如果视频 > 60 秒，使用 `analyze_video` 提交异步任务
3. **查询异步结果**：提交异步任务后，等待 30 秒再用 `get_task_status` 查询
4. **总结内容**：分析完成后，向用户总结视频的关键内容

**有效的提问方式：**
- "视频中展示了什么活动？"
- "请总结视频的主要内容"
- "视频中的人物在做什么？"
- "这个教程的步骤是什么？"

**注意事项：**
- 视频路径必须是绝对路径
- 异步任务可能需要 2-5 分钟完成
- 如果只需要了解视频基本信息，使用 `get_video_info` 即可，不消耗 AI 资源""",
                    ),
                )
            ],
        )
    raise ValueError(f"Prompt not found: {name}")


async def main():
    """Main entry point."""
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async with stdio_server(server) as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="video-analyzer-mcp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
```

### pyproject.toml

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "video-analyzer-mcp"
version = "0.1.0"
authors = [
    { name="Your Name", email="your.email@example.com" },
]
description = "MCP server for video-analyzer"
readme = "README.md"
requires-python = ">=3.8"
classifiers = [
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: Apache Software License",
    "Operating System :: OS Independent",
]
dependencies = [
    "mcp>=1.0.0",
    "video-analyzer>=0.1.2",
]

[project.scripts]
video-analyzer-mcp = "video_analyzer_mcp.server:main"
```

---

## 部署与运行

### 1. 环境准备

确保已安装 `video-analyzer` 及其依赖：

```bash
# 安装 video-analyzer
pip install -e /path/to/video-analyzer

# 安装 FFmpeg
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y ffmpeg
```

确保 Ollama 正在运行（如果使用本地模式）：

```bash
ollama serve
ollama pull llama3.2-vision
```

### 2. 安装 MCP 服务器

```bash
# 方式一：pip 安装（发布后）
pip install video-analyzer-mcp

# 方式二：本地开发安装
cd video-analyzer-mcp
pip install -e .
```

### 3. 运行 MCP 服务器

```bash
# stdio 模式（推荐，用于 Claude Desktop 等本地客户端）
video-analyzer-mcp

# 或直接用 Python
python -m video_analyzer_mcp.server
```

---

## 分享给他人使用

### 方式一：PyPI 发布（推荐）

1. **准备发布包：**

```bash
cd video-analyzer-mcp
python -m build
```

2. **上传到 PyPI：**

```bash
python -m twine upload dist/*
```

3. **用户安装：**

```bash
pip install video-analyzer-mcp
```

### 方式二：GitHub 仓库安装

如果不想发布到 PyPI，可以直接从 GitHub 安装：

```bash
pip install git+https://github.com/yourname/video-analyzer-mcp.git
```

在 README 中提供安装说明：

```markdown
## 安装

```bash
# 安装 MCP 服务器
pip install video-analyzer-mcp

# 确保 video-analyzer 依赖已安装
pip install video-analyzer

# 安装 FFmpeg
brew install ffmpeg  # macOS
sudo apt-get install ffmpeg  # Ubuntu
```

## 配置

将以下配置添加到你的 MCP 客户端（Claude Desktop / Cursor / Cline 等）：

```json
{
  "mcpServers": {
    "video-analyzer": {
      "command": "video-analyzer-mcp",
      "args": []
    }
  }
}
```
```

### 方式三：Docker 部署

提供 Dockerfile，方便无 Python 环境的用户使用：

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg

RUN pip install video-analyzer-mcp video-analyzer

ENTRYPOINT ["video-analyzer-mcp"]
```

构建和运行：

```bash
docker build -t video-analyzer-mcp .
docker run -i --rm video-analyzer-mcp
```

---

## 客户端配置示例

### Claude Desktop (macOS)

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "video-analyzer": {
      "command": "/path/to/.venv/bin/video-analyzer-mcp",
      "args": []
    }
  }
}
```

### Cursor

在 Cursor Settings → MCP 中添加：

```json
{
  "mcpServers": [
    {
      "name": "video-analyzer",
      "command": "video-analyzer-mcp",
      "type": "command"
    }
  ]
}
```

### Cline (VS Code 插件)

在 Cline 设置中添加 MCP 服务器：

```json
{
  "mcpServers": {
    "video-analyzer": {
      "command": "video-analyzer-mcp",
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

### 使用 uv 运行（无需全局安装）

如果你使用 `uv` 包管理器，可以无需全局安装直接运行：

```json
{
  "mcpServers": {
    "video-analyzer": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "video-analyzer-mcp",
        "video-analyzer-mcp"
      ]
    }
  }
}
```

---

## 注意事项与最佳实践

### 1. 超时问题

| 工具 | 建议超时 | 原因 |
|---|---|---|
| `analyze_video` | N/A（异步） | 立即返回 task_id |
| `analyze_video_quick` | 120 秒 | 限 60 秒视频，约需 30-90 秒 |
| `get_video_info` | 10 秒 | 纯 ffprobe，很快 |
| `get_task_status` | 10 秒 | 内存查询，很快 |

### 2. 资源消耗

- **GPU 内存**：Whisper 模型会占用显存，建议限制并发任务数为 1
- **磁盘空间**：临时帧文件可能占用数百 MB，及时清理
- **LLM 调用费用**：每帧调用一次视觉模型，30 帧视频 = 30 次 API 调用

### 3. 并发控制

生产环境建议添加任务队列：

```python
# 使用 asyncio.Semaphore 限制并发
_semaphore = asyncio.Semaphore(1)  # 同时只运行 1 个分析任务

async def run_analysis(task_id: str, args: dict):
    async with _semaphore:
        # 实际分析逻辑
        ...
```

### 4. 错误处理

Agent 可能传入无效路径或损坏的视频文件，确保所有工具都有健壮的错误处理：

```python
# 检查文件存在性和格式
if not video_path.exists():
    return [TextContent(type="text", text="错误：文件不存在")]

if video_path.suffix.lower() not in ['.mp4', '.avi', '.mov', '.mkv']:
    return [TextContent(type="text", text="错误：不支持的格式")]
```

### 5. 安全性

- **路径验证**：确保 Agent 只能访问允许的视频文件路径
- **命令注入**：不要直接将 Agent 输入拼接到 shell 命令中
- **资源限制**：设置最大文件大小和最长视频时长限制

### 6. 配置热加载

MCP 服务器启动时读取 `config/config.json`，支持 Ollama 和 OpenAI API 切换：

```python
# 启动时检查配置
config = Config("config")
client_type = config.get("clients", {}).get("default", "ollama")
logger.info(f"使用客户端: {client_type}")
```

---

## 总结

将 `video-analyzer` 封装为 MCP 服务器的核心价值：

1. **标准化接口** —— 任何支持 MCP 的 Agent 都能调用
2. **异步处理** —— 长视频分析不阻塞 Agent
3. **能力复用** —— Agent 获得"看懂视频"的能力
4. **易于分享** —— pip 安装即可使用

**推荐实现路径：**

1. 先实现 **方案三（混合模式）** 的 `analyze_video` + `get_task_status` + `get_video_info`
2. 发布到 PyPI 或提供 GitHub 安装方式
3. 收集使用反馈，逐步添加 `analyze_video_quick` 和更多工具
