"""video-analyzer 两个提示词的 DSPy 签名。"""

import dspy


class FrameAnalysisSignature(dspy.Signature):
    """分析单个视频帧，生成关于可见内容的简洁笔记，
    并将观察结果与此前已分析帧的上下文关联起来。"""

    image: dspy.Image = dspy.InputField(
        desc="要分析的视频帧图像"
    )
    previous_frames: str = dspy.InputField(
        desc="按时间顺序排列的此前已分析帧的笔记"
    )
    user_question: str = dspy.InputField(
        desc="用户的问题或分析关注焦点"
    )
    frame_note: str = dspy.OutputField(
        desc="关于本帧的简洁笔记，包含场景、动作和关键延续要点"
    )


class ReconstructionSignature(dspy.Signature):
    """将按时间顺序排列的帧笔记和音频转录文本综合成连贯的视频描述。"""

    frame_notes: str = dspy.InputField(
        desc="所有已分析帧的按时间顺序排列的笔记"
    )
    first_frame_note: str = dspy.InputField(
        desc="第一帧的分析结果，用于锚定描述"
    )
    transcript: str = dspy.InputField(
        desc="视频的音频转录文本（如果未检测到音频则可能为空）"
    )
    user_question: str = dspy.InputField(
        desc="用户的问题或描述关注焦点"
    )
    description: str = dspy.OutputField(
        desc="对视频内容的全面、连贯的描述"
    )


class DescriptionJudgeSignature(dspy.Signature):
    """将视频描述与理想参考描述进行比较，评估其质量。"""

    ideal: str = dspy.InputField(
        desc="理想的参考描述"
    )
    candidate: str = dspy.InputField(
        desc="要评估的候选描述"
    )
    user_question: str = dspy.InputField(
        desc="用户的原始问题或关注焦点"
    )
    score: int = dspy.OutputField(
        desc="质量评分，1（差）到 5（优秀），考虑覆盖度、准确性和与用户问题的相关性"
    )


class FrameNoteJudgeSignature(dspy.Signature):
    """将帧分析笔记与理想参考笔记进行比较，评估其质量。"""

    ideal: str = dspy.InputField(
        desc="理想的参考帧笔记"
    )
    candidate: str = dspy.InputField(
        desc="要评估的候选帧笔记"
    )
    score: int = dspy.OutputField(
        desc="质量评分，1（差）到 5（优秀），考虑细节、准确性以及对视频重建的有用性"
    )