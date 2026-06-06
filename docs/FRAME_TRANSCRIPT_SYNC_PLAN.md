# 转录文字与关键帧时间戳对齐方案

> 状态：待评审  
> 作者：Claude  
> 日期：2026-06-07

---

## 1. 现状分析

### 1.1 当前数据流

```
视频输入
    ├── 帧提取 (VideoProcessor)
    │     └── 输出：Frame[]  (含 timestamp, path, score)
    │
    └── 音频提取 + 转录 (AudioProcessor)
          └── 输出：AudioTranscript
                ├── text: 纯文本
                └── segments: [{text, start, end, words[]}]

帧分析阶段
    └── 逐帧送入 LLM，生成 frame_analyses[]

视频重建阶段
    └── frame_analyses[] + transcript.text → LLM → video_description
```

### 1.2 当前问题

| 问题 | 说明 |
|------|------|
| 时间戳信息丢失 | 重建阶段只用了 `transcript.text`（纯文本），`segments` 的时间戳被丢弃 |
| 无法精确对应 | LLM 只能"模糊"关联文字和画面，无法确定"第 5 秒说了什么 + 第 5 秒的画面是什么" |
| 输出结构松散 | `analysis.json` 中 transcript 和 frame_analyses 是两个独立数组，没有交叉引用 |

---

## 2. 目标

在 `analysis.json` 中新增一个按时间轴对齐的数据结构，实现：

1. **时间段划分**：按关键帧时间戳把视频切成若干时间区间
2. **内容聚合**：每个区间包含该区间内的帧截图 + 对应转录文字
3. **LLM 感知**：视频重建提示词中包含时间对齐信息，让模型输出更精确
4. **可追溯**：用户能从结果直接定位"某句话出现在视频的哪个画面"

---

## 3. 方案设计

### 3.1 输出结构（目标 JSON）

在 `analysis.json` 中新增 `synced_timeline` 字段：

```json
{
  "metadata": { ... },
  "transcript": { ... },
  "frame_analyses": [ ... ],
  "video_description": { ... },
  "synced_timeline": [
    {
      "index": 0,
      "time_start": 0.0,
      "time_end": 5.43,
      "frames": [
        {
          "frame_index": 0,
          "timestamp": 0.0,
          "path": "output/frames/frame_0.jpg",
          "analysis": "画面中有演讲者在讲台前..."
        }
      ],
      "transcript_segments": [
        {
          "text": "大家好，欢迎来到本次分享。",
          "start": 0.5,
          "end": 3.2
        }
      ]
    },
    {
      "index": 1,
      "time_start": 5.43,
      "time_end": 12.80,
      "frames": [
        {
          "frame_index": 1,
          "timestamp": 5.43,
          "path": "output/frames/frame_1.jpg",
          "analysis": "演讲者翻到PPT第二页，展示架构图..."
        }
      ],
      "transcript_segments": [
        {
          "text": "今天我们要介绍的是整体架构设计。",
          "start": 5.8,
          "end": 9.1
        },
        {
          "text": "首先看一下模块划分。",
          "start": 9.5,
          "end": 11.2
        }
      ]
    }
  ]
}
```

### 3.2 对齐算法

```
输入：frames[] (按 timestamp 排序), segments[] (按 start 排序)
输出：timeline[]

算法步骤：
1. 生成时间区间边界
   boundaries = [0] + [f.timestamp for f in frames[1:]] + [video_duration]
   区间 i 的范围：[boundaries[i], boundaries[i+1])

2. 每个区间分配帧
   timeline[i].frames = frames[i]  （区间 i 的左边界帧）

3. 每个区间分配转录片段
   对于每个 segment，找到满足 overlap 的区间：
   overlap = segment 的时间范围与区间时间范围的交集
   如果 overlap > 0，将该 segment 归入对应区间

4. 边界情况处理
   - 区间开始时无转录（静音段）→ transcript_segments 为空数组
   - 同一 segment 跨越多个区间 → 允许出现在多个区间中（或按 start 时间归入最近的区间）
```

### 3.3 核心改动点

#### A. 新增 `TimelineSync` 类（建议文件：`video_analyzer/timeline.py`）

```python
@dataclass
class TimelineSlot:
    index: int
    time_start: float
    time_end: float
    frames: List[Dict[str, Any]]      # 帧索引 + 分析结果
    transcript_segments: List[Dict[str, Any]]  # 转录片段

class TimelineSync:
    def __init__(self, frames: List[Frame], frame_analyses: List[Dict],
                 transcript: Optional[AudioTranscript], video_duration: float):
        ...

    def build(self) -> List[TimelineSlot]:
        """按时间戳对齐帧和转录片段。"""
        ...

    def format_for_llm(self) -> str:
        """生成适合插入提示词的对齐文本。"""
        ...
```

#### B. 修改 `analyzer.py`

**修改点 1：重构 `reconstruct_video` 方法**

当前：`transcript_text = transcript.text`（纯文本）

改为：
```python
from .timeline import TimelineSync

def reconstruct_video(self, frame_analyses, frames, transcript=None):
    # 构建时间轴对齐数据
    timeline = TimelineSync(frames, frame_analyses, transcript, video_duration)
    slots = timeline.build()

    # 生成提示词用的时间轴文本
    timeline_text = timeline.format_for_llm()

    # 替换提示词中的占位符
    prompt = self.video_prompt.replace("{TRANSCRIPT}", transcript.text if transcript else "")
    prompt = prompt.replace("{TIMELINE}", timeline_text)
    ...
```

**修改点 2：提示词模板新增 `{TIMELINE}` 占位符**

在 `video_analyzer/prompts/frame_analysis/describe.txt` 中新增：

```
Timeline-Aligned Content

{TIMELINE}

注意：以上时间轴将每帧画面与对应时间段的转录文字进行了对齐，
请在总结时利用这些信息，确保描述与时间顺序一致。
```

#### C. 修改 `cli.py`

在结果组装阶段（约第 177-196 行），新增 `synced_timeline` 字段：

```python
results = {
    "metadata": { ... },
    "transcript": { ... },
    "frame_analyses": frame_analyses,
    "video_description": video_description,
    "synced_timeline": [
        {
            "index": slot.index,
            "time_start": slot.time_start,
            "time_end": slot.time_end,
            "frames": [{
                "frame_index": f.number,
                "timestamp": f.timestamp,
                "path": str(f.path),
                "analysis": fa.get("response", "")
            } for f, fa in zip(slot.frames, slot.frame_analyses)],
            "transcript_segments": slot.transcript_segments
        }
        for slot in timeline_slots
    ]
}
```

---

## 4. 改动范围统计

| 文件 | 操作 | 说明 |
|------|------|------|
| `video_analyzer/timeline.py` | **新增** | 核心对齐逻辑 |
| `video_analyzer/analyzer.py` | 修改 | 集成 TimelineSync，修改 reconstruct_video |
| `video_analyzer/cli.py` | 修改 | 结果 JSON 中新增 synced_timeline 字段 |
| `video_analyzer/prompts/frame_analysis/describe.txt` | 修改 | 新增 `{TIMELINE}` 占位符和相关指令 |
| `video_analyzer/prompt.py` | 可能修改 | 如果 PromptLoader 需要支持新占位符的默认行为 |

---

## 5. 边界情况处理

| 场景 | 处理策略 |
|------|----------|
| 视频无音频 / 转录失败 | `synced_timeline` 中所有 `transcript_segments` 为空数组 |
| 某区间无关键帧（帧数极少时）| 跳过该区间，或以视频边界强制生成 |
| segment 跨越多个区间 | **方案 A**：允许重复出现；**方案 B**：按 segment.start 归入最近的区间（推荐 B，简单明确） |
| 静音段（无 transcript）| `transcript_segments` 为空数组，正常保留帧信息 |
| 帧分析失败（某帧报错）| 使用错误信息作为 analysis 字段值，不影响对齐 |

---

## 6. 向后兼容性

- `analysis.json` 新增字段，旧字段（`transcript`、`frame_analyses`、`video_description`）**保持不变**
- 不启用对齐功能时（如不传 transcript），`synced_timeline` 可为 `null` 或空数组
- 命令行参数和配置文件 schema **无需变更**
- 提示词模板中 `{TIMELINE}` 为空字符串时，不影响原有逻辑

---

## 7. 实施步骤建议

1. **Step 1**：新建 `timeline.py`，实现 `TimelineSync.build()` 和单元测试
2. **Step 2**：修改 `analyzer.py`，在 `reconstruct_video` 中调用 TimelineSync，生成 `{TIMELINE}` 文本
3. **Step 3**：修改 `describe.txt` 提示词模板，插入 `{TIMELINE}` 占位符
4. **Step 4**：修改 `cli.py`，把 `synced_timeline` 写入 `analysis.json`
5. **Step 5**：端到端测试，验证各种边界情况

---

## 8. 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|----------|
| 对齐算法复杂度过高 | 低 | 算法仅为简单的区间划分 + 交集判断，O(n·m) 即可 |
| 提示词长度膨胀 | 中 | Timeline 格式化文本会比纯 transcript 长，需关注长视频场景；可选项：精简格式或截断 |
| LLM 输出质量下降 | 低 | 对齐信息是补充而非替代，原有 `{TRANSCRIPT}` 保留 |
| 向后兼容破坏 | 低 | 纯新增字段，不改动现有 schema |

---

## 9. 替代方案（轻量级）

如果完整方案太重，可以考虑**简化版**：

不新增 `synced_timeline` 数据结构，只在 `describe.txt` 提示词中，把 transcript segments 按时间戳分段输出，让 LLM "自行"关联：

```
Transcript (with timestamps):
[0.0s - 3.2s] 大家好，欢迎来到本次分享。
[3.5s - 8.1s] 今天我们要介绍的是...

Frame Notes:
Frame 0 (0.0s): ...
Frame 1 (5.4s): ...
```

这种方式：
- ✅ 不改 Python 代码，只改提示词模板
- ❌ 没有结构化输出，用户无法从 JSON 中直接读取对齐关系