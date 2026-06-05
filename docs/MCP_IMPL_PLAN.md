# Video Analyzer MCP —— 独立实现方案

本文档是 `MCP_DESIGN.md` 的补充，详细描述**方案二（完全独立、内嵌业务逻辑）**的实现规划。基于以下约束条件设计：

- **仅支持 OpenAI 兼容协议的视觉模型**（OpenRouter、OpenAI、Azure 等），**不支持 Ollama**
- **仅支持 stdio 传输模式**（面向 Claude Desktop、Cursor、Cline 等本地客户端）
- **并发限制为 1**（串行处理，避免 GPU/内存溢出）
- **不依赖 `video-analyzer` 包**，所有业务逻辑内嵌

## 目录

- [总体架构](#总体架构)
- [文件结构](#文件结构)
- [模块设计](#模块设计)
- [依赖清单](#依赖清单)
- [配置方式](#配置方式)
- [关键设计决策](#关键设计决策)
- [实现顺序](#实现顺序)
- [风险与应对](#风险与应对)

---

## 总体架构

```
┌──────────────────────────────────────────┐
│  AI Agent (Claude Desktop / Cursor / Cline) │
│                                          │
│  MCP stdio 协议                          │
└──────────────┬───────────────────────────┘
               │
┌──────────────▼───────────────────────────┐
│       video-analyzer-mcp (独立包)         │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  server.py —— MCP 协议层            │  │  全新编写
│  │  • list_tools / call_tool           │  │
│  │  • stdio_server 入口                │  │
│  └────────────────────────────────────┘  │
│  ┌────────────────────────────────────┐  │
│  │  task_manager.py —— 任务队列        │  │  全新编写
│  │  • 内存存储 + asyncio.Semaphore(1)  │  │
│  └────────────────────────────────────┘  │
│  ┌────────────────────────────────────┐  │
│  │  analyzer_core.py —— 分析引擎       │  │  从原库复制
│  │  • analyze_frame()                  │  │
│  │  • reconstruct_video()              │  │
│  └────────────────────────────────────┘  │
│  ┌────────────────────────────────────┐  │
│  │  frame_extractor.py —— 帧提取       │  │  从原库复制
│  │  • extract_keyframes()              │  │
│  └────────────────────────────────────┘  │
│  ┌────────────────────────────────────┐  │
│  │  audio_processor.py —— 音频处理     │  │  从原库精简
│  │  • extract_audio() / transcribe()   │  │
│  └────────────────────────────────────┘  │
│  ┌────────────────────────────────────┐  │
│  │  llm_client.py —— OpenAI 客户端     │  │  从原库复制+简化
│  │  • 仅保留 GenericOpenAIAPIClient     │  │
│  └────────────────────────────────────┘  │
│  ┌────────────────────────────────────┐  │
│  │  config.py —— 简化配置              │  │  重写
│  │  • dataclass + 环境变量             │  │
│  └────────────────────────────────────┘  │
│  ┌────────────────────────────────────┐  │
│  │  prompts/ —— 提示词文件             │  │  从原库复制
│  │  • frame_analysis.txt               │  │
│  │  • describe.txt                     │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
               │
        ┌──────┴──────┐
        ▼             ▼
   FFmpeg       faster-whisper
  (视频处理)     (音频转录)
        │             │
        └──────┬──────┘
               ▼
        OpenAI 兼容 API
        (视觉大语言模型)
```

---

## 文件结构

```
video-analyzer-mcp/
├── pyproject.toml
├── README.md
└── video_analyzer_mcp/
    ├── __init__.py
    ├── server.py              # MCP 协议层（~250 行，全新）
    ├── task_manager.py        # 异步任务管理（~100 行，全新）
    ├── analyzer_core.py       # 视频分析引擎（~125 行，复制）
    ├── frame_extractor.py     # 帧提取（~150 行，复制）
    ├── audio_processor.py     # 音频处理（~120 行，复制+精简）
    ├── llm_client.py          # OpenAI 兼容客户端（~130 行，复制+简化）
    ├── config.py              # 配置管理（~50 行，重写简化）
    └── prompts/
        ├── frame_analysis.txt   # 帧分析提示词（从原库复制）
        └── describe.txt         # 视频重建提示词（从原库复制）
```

**总计约 925 行代码**，其中 350 行全新编写，575 行从原库复制/精简。

---

## 模块设计

### 1. `llm_client.py` —— 仅保留 OpenAI 兼容客户端

**来源：** `video_analyzer/clients/generic_openai_api.py`

**改动：**
- 删除 `OllamaClient` 类（不支持本地模型）
- 删除 `LLMClient` 抽象基类（只剩一个实现，无需抽象）
- 删除 `stream` 参数支持（MCP 工具调用不需要流式）
- 保留重试逻辑和速率限制处理

```python
class OpenAICompatibleClient:
    def __init__(self, api_key: str, api_url: str, max_retries: int = 3): ...
    def generate(self, prompt: str, image_path: str | None = None,
                 model: str = "", temperature: float = 0.2,
                 max_tokens: int = 256) -> dict[str, Any]: ...
```

**输入输出格式保持不变：** 返回 `{"response": "..."}`，与 `analyzer_core.py` 兼容。

---

### 2. `frame_extractor.py` —— 直接复制

**来源：** `video_analyzer/frame.py`

**保留内容：**
- `Frame` dataclass（`number`, `timestamp`, `path`）
- `VideoProcessor` 类及其 `extract_keyframes()` 方法
- 完整的帧选择算法（目标计算 → 自适应采样 → 差异分析 → 最终选择）

**改动：**
- 无。该模块纯算法，与原库解耦。

**依赖：** `opencv-python`, `numpy`

---

### 3. `audio_processor.py` —— 复制并精简

**来源：** `video_analyzer/audio_processor.py`

**保留内容：**
- `AudioTranscript` dataclass
- `AudioProcessor` 类的 `extract_audio()` 和 `transcribe()`

**砍掉的内容：**
- 语言代码白名单验证（`accepted_languages` 集合）→ 改为 try-catch，让 Whisper 自动检测
- pydub fallback（假设 FFmpeg 已安装）→ 保留但降级为 warning，不阻断流程

**依赖：** `faster-whisper`, `pydub`

---

### 4. `analyzer_core.py` —— 直接复制，仅改导入

**来源：** `video_analyzer/analyzer.py`

**保留内容（一字不改）：**
- `VideoAnalyzer.__init__()`
- `VideoAnalyzer.analyze_frame()` —— 逐帧分析核心
- `VideoAnalyzer.reconstruct_video()` —— 视频重建核心
- `_format_user_prompt()`, `_format_previous_analyses()`, `_load_prompts()`

**唯一改动：** 导入路径从 `video_analyzer.xxx` 改为同级相对导入 `.xxx`

> ⚠️ **关键原则：** 该模块是业务核心，逻辑必须与原库完全一致，否则输出格式会变，提示词文件中的 `{TOKEN}` 占位符替换逻辑也必须一致。

---

### 5. `config.py` —— 大幅简化

**来源：** `video_analyzer/config.py`（仅参考设计理念）

**原库复杂度：** 级联配置（命令行 > 用户 JSON > 默认 JSON）+ pkg_resources 资源加载 + 参数映射

**简化后：** 纯 dataclass，从环境变量读取

```python
@dataclass
class Config:
    api_key: str
    api_url: str
    model: str = "gpt-4o"
    temperature: float = 0.2
    frames_per_minute: int = 10
    max_frames: int = 30
    whisper_model: str = "medium"
    whisper_device: str = "cpu"
    audio_language: str | None = None

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            api_key=os.environ["VIDEO_ANALYZER_API_KEY"],
            api_url=os.environ.get("VIDEO_ANALYZER_API_URL", "https://api.openai.com/v1"),
            model=os.environ.get("VIDEO_ANALYZER_MODEL", "gpt-4o"),
            ...
        )
```

**环境变量清单：**

| 变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `VIDEO_ANALYZER_API_KEY` | **是** | — | API 密钥 |
| `VIDEO_ANALYZER_API_URL` | 否 | `https://api.openai.com/v1` | API 端点 |
| `VIDEO_ANALYZER_MODEL` | 否 | `gpt-4o` | 视觉模型名称 |
| `VIDEO_ANALYZER_TEMPERATURE` | 否 | `0.2` | 生成温度 |
| `VIDEO_ANALYZER_FPM` | 否 | `10` | 每分钟提取帧数 |
| `VIDEO_ANALYZER_MAX_FRAMES` | 否 | `30` | 最大帧数 |
| `VIDEO_ANALYZER_WHISPER_MODEL` | 否 | `medium` | Whisper 模型 |
| `VIDEO_ANALYZER_WHISPER_DEVICE` | 否 | `cpu` | Whisper 运行设备 |
| `VIDEO_ANALYZER_LANGUAGE` | 否 | — | 音频语言（如 `zh`、`en`） |

---

### 6. `task_manager.py` —— 全新编写

**职责：** 管理异步视频分析任务，限制并发为 1

```python
class TaskManager:
    def __init__(self, config: Config):
        self.config = config
        self.tasks: dict[str, Task] = {}           # 内存存储
        self.semaphore = asyncio.Semaphore(1)      # 并发限制

    async def submit(self, video_path: str, **options) -> str:
        """提交任务，立即返回 task_id"""
        task_id = generate_id()
        self.tasks[task_id] = Task(id=task_id, status="pending")
        asyncio.create_task(self._run(task_id, video_path, **options))
        return task_id

    async def _run(self, task_id: str, video_path: str, **options):
        """在后台执行三阶段分析流水线"""
        async with self.semaphore:                   # 串行执行
            task = self.tasks[task_id]
            task.status = "processing"
            task.stage = "frame_extraction"

            # Stage 1: 帧 + 音频提取
            frames = extract_keyframes(video_path, ...)
            transcript = extract_and_transcribe_audio(video_path, ...)
            task.progress = 30

            # Stage 2: 逐帧分析
            task.stage = "frame_analysis"
            frame_analyses = []
            for i, frame in enumerate(frames):
                analysis = analyzer.analyze_frame(frame)
                frame_analyses.append(analysis)
                task.progress = 30 + int((i + 1) / len(frames) * 60)

            # Stage 3: 视频重建
            task.stage = "reconstruction"
            description = analyzer.reconstruct_video(frame_analyses, frames, transcript)
            task.progress = 100
            task.status = "completed"
            task.result = build_result(description, transcript, frame_analyses)

    def get_status(self, task_id: str) -> dict | None:
        """查询任务状态"""
        ...
```

**Task 数据结构：**

```python
@dataclass
class Task:
    id: str
    status: Literal["pending", "processing", "completed", "failed"]
    stage: str = "initialized"
    progress: int = 0          # 0-100
    video_path: str = ""
    result: dict | None = None
    error: str | None = None
    created_at: float = 0.0
```

---

### 7. `server.py` —— MCP 协议层

**职责：** 实现 MCP 协议，暴露 4 个 Tool

**暴露的工具：**

| 工具 | 模式 | 说明 |
|---|---|---|
| `analyze_video` | 异步 | 提交分析任务，返回 `task_id` |
| `get_task_status` | 同步 | 查询任务状态/结果 |
| `get_video_info` | 同步 | 获取视频元信息（ffprobe，不调用 AI） |
| `list_tasks` | 同步 | 列出最近任务 |

**砍掉的原设计工具：**
- ❌ `analyze_video_quick` —— 有并发限制为 1，同步异步没区别，统一走异步更干净
- ❌ Resource / Prompt —— 先不实现，降低复杂度

**stdio 入口：**

```python
async def main():
    config = Config.from_env()
    task_manager = TaskManager(config)
    server = Server("video-analyzer")

    @server.list_tools()
    async def list_tools() -> list[Tool]: ...

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]: ...

    async with stdio_server(server) as (read_stream, write_stream):
        await server.run(read_stream, write_stream, ...)
```

---

## 依赖清单

```toml
[project]
dependencies = [
    # MCP 协议层
    "mcp>=1.0.0",

    # 视频处理
    "opencv-python>=4.8.0",
    "numpy>=1.24.0",

    # 音频转录
    "faster-whisper>=0.6.0",
    "pydub>=0.25.1",

    # 其他工具
    "requests>=2.31.0",
    "Pillow>=10.0.0",
    "torch>=2.0.0",
]
```

**系统依赖（需用户自行安装）：**
- Python 3.11+
- FFmpeg

**砍掉的原库依赖：**
- ❌ `openai-whisper`（`faster-whisper` 已覆盖）
- ❌ `pkg_resources`（不再内嵌包资源）

---

## 配置方式

由于仅支持 stdio 模式，配置通过**环境变量**传入。MCP 客户端（如 Claude Desktop）在启动子进程时会继承环境变量。

### Claude Desktop 配置示例

```json
{
  "mcpServers": {
    "video-analyzer": {
      "command": "/path/to/venv/bin/video-analyzer-mcp",
      "env": {
        "VIDEO_ANALYZER_API_KEY": "sk-xxx",
        "VIDEO_ANALYZER_API_URL": "https://openrouter.ai/api/v1",
        "VIDEO_ANALYZER_MODEL": "meta-llama/llama-3.2-11b-vision-instruct",
        "VIDEO_ANALYZER_FPM": "10",
        "VIDEO_ANALYZER_MAX_FRAMES": "30",
        "VIDEO_ANALYZER_WHISPER_MODEL": "medium",
        "VIDEO_ANALYZER_WHISPER_DEVICE": "cpu"
      }
    }
  }
}
```

### 不同服务商的配置

**OpenRouter：**
```json
"VIDEO_ANALYZER_API_URL": "https://openrouter.ai/api/v1",
"VIDEO_ANALYZER_MODEL": "meta-llama/llama-3.2-11b-vision-instruct"
```

**OpenAI：**
```json
"VIDEO_ANALYZER_API_URL": "https://api.openai.com/v1",
"VIDEO_ANALYZER_MODEL": "gpt-4o"
```

**Azure OpenAI：**
```json
"VIDEO_ANALYZER_API_URL": "https://your-resource.openai.azure.com/openai/deployments/your-deployment",
"VIDEO_ANALYZER_MODEL": "gpt-4o"
```

---

## 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| **本地模型** | ❌ 不支持 Ollama | 减少维护面，OpenAI 协议已覆盖绝大多数服务商 |
| **传输模式** | stdio only | 面向本地客户端，实现最简单 |
| **并发** | 1（串行） | Whisper 模型加载占显存，视觉模型每帧调用 API，串行最安全 |
| **任务存储** | 内存 dict | 简单够用，MCP 子进程随客户端生命周期，无需持久化 |
| **配置方式** | 环境变量 | stdio 模式下最自然的配置方式 |
| **输出保留** | 分析完删除 | 节省磁盘，只保留 `analysis.json` 在内存中返回 |
| **快速模式** | ❌ 不实现 | 并发已限 1，同步异步无区别，统一异步更干净 |
| **Resource/Prompt** | ❌ 暂不实现 | 先降低复杂度，后续有需要再添加 |
| **视频输入** | 文件绝对路径 | 最简单，Agent 负责把视频放到服务器可访问的位置 |

---

## 实现顺序

### 第 1 步：搭骨架（~1 小时）

创建项目结构和空壳：

```
video-analyzer-mcp/
├── pyproject.toml              # 定义包名、依赖、入口点
├── README.md                   # 安装和配置说明
└── video_analyzer_mcp/
    ├── __init__.py
    ├── server.py               # MCP 协议层空壳
    │   ├── list_tools() → 返回空列表
    │   ├── call_tool() → 返回占位文本
    │   └── main() → stdio_server 入口
    └── prompts/
        ├── frame_analysis.txt   # 从原库复制
        └── describe.txt         # 从原库复制
```

**验证：** `pip install -e .` 后 `video-analyzer-mcp` 命令能启动不报错。

### 第 2 步：内嵌业务逻辑（~2 小时）

复制/精简核心模块：

```
video_analyzer_mcp/
├── llm_client.py               # 从 generic_openai_api.py 复制，删掉 Ollama
├── frame_extractor.py          # 从 frame.py 完整复制
├── audio_processor.py          # 从 audio_processor.py 复制，砍掉语言白名单
├── analyzer_core.py            # 从 analyzer.py 复制，改导入路径
└── config.py                   # 重写简化版 dataclass
```

**验证：** 写一个独立测试脚本，直接调用 `VideoAnalyzer.analyze_frame()` 跑通一帧分析。

### 第 3 步：连接层（~1.5 小时）

```
video_analyzer_mcp/
├── task_manager.py             # 全新：任务提交 + 异步执行 + 并发限制
└── server.py                   # 填充：4 个 Tool 的具体实现
```

**验证：** 端到端跑通一个短视频分析：`analyze_video` → `get_task_status` → 拿到描述结果。

### 第 4 步： polish（~1 小时）

- 添加错误处理（文件不存在、格式不支持、API 失败）
- 添加日志输出（方便调试）
- README 完善（安装、配置、使用示例）
- 测试不同视频（有声/无声、长/短、不同格式）

---

## 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| **analyzer_core 复制后行为不一致** | 输出格式改变 | 复制后不做任何逻辑改动，仅改 import 路径；用同一视频对比原库和新库输出 |
| **MCP 协议版本变动** | 需要迁移 | `mcp>=1.0.0` 目前稳定，API 变更风险低 |
| **Whisper 模型首次加载慢** | 首次任务等待时间长 | 在 `task_manager.__init__` 中预加载 Whisper 模型（可选优化） |
| **API 费用不可控** | 长视频帧数多，调用次数多 | 默认 `max_frames=30`，Agent 可通过参数限制；文档中明确说明费用模型 |
| **大视频文件导致磁盘满** | 临时帧文件占用空间 | 分析完成后立即删除 `frames/` 目录，只保留内存中的结果 |
| **并发虽然限制为 1，但 Agent 可并行提交多个 MCP 服务器** | 资源竞争 | 这是 Agent 端问题，文档中说明不要配置多个实例 |

---

## 与原库的依赖关系图

```
                    video-analyzer-mcp (独立包)
                           │
    ┌──────────────────────┼──────────────────────┐
    │                      │                      │
    ▼                      ▼                      ▼
 llm_client.py      frame_extractor.py     audio_processor.py
 (复制+简化)          (直接复制)            (复制+精简)
    │                      │                      │
    ▼                      ▼                      ▼
 requests              opencv-python          faster-whisper
 (pip)                 (pip)                  (pip)
    │                      │                      │
    └──────────────────────┼──────────────────────┘
                           │
                           ▼
                    analyzer_core.py
                       (直接复制)
                           │
                           ▼
                    task_manager.py
                    server.py (MCP)
                           │
                           ▼
                        mcp (pip)
```

**与原库零依赖** —— 不 `import video_analyzer`，所有业务逻辑内嵌。

---

## 总结

在约束条件（仅 OpenAI 协议、stdio only、并发=1）下，实现工作量约 **4 个模块复制 + 2 个模块重写 + 1 个模块全新编写**，总计约 925 行代码，预估 **5–6 小时**完成。

核心风险在于 `analyzer_core.py` 必须与原库行为完全一致，复制后不做任何逻辑改动即可规避。

确认这个方案后，我可以按**第 1 步 → 第 2 步 → 第 3 步 → 第 4 步**的顺序逐块实现。
