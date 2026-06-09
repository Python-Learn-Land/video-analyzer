#!/usr/bin/env python3
"""
Sequential batch runner for Kimi Code CLI over MP4 files.

Usage:
    python kimi_batch_mp4.py /path/to/videos "Summarize this video and extract key timestamps."

For each .mp4 in the target folder, the script runs:
    kimi -p "<video path=\"...\"></video>\n<your prompt>"

It waits for each command to finish before starting the next one.


用法示例

# 基础用法：处理当前目录下所有 mp4
python kimi_batch_mp4.py /path/to/videos "请总结这个视频的内容并提取关键时间戳。"

# 递归查找子目录里的 mp4
python kimi_batch_mp4.py /path/to/videos "分析视频内容" -r

# 某个命令失败时停止
python kimi_batch_mp4.py /path/to/videos "转录并总结" --stop-on-error

# 只打印会执行什么，不真跑
python kimi_batch_mp4.py /path/to/videos "总结" --dry-run

脚本做了什么

1. 按文件名排序列出文件夹里的 .mp4
2. 对每个文件构造这样的 prompt：
<video path="/absolute/path/to/video.mp4"></video>

你的提示词...
3. 执行：
kimi -p "<上面的 prompt>"
4. 等当前命令完全结束再开始下一个（顺序执行，不会并发）
5. 最后汇报成功/失败数量

重要提醒

结合你前面问的两点：

- -p 模式下 @文件 不会被 CLI 自动处理，所以我用了 <video path="..."> 标签。这个格式在 Kimi Code 内部是用来触发 ReadMediaFile 工具的，模型看到后会主动去读取视频。
- -p 模式不会等人确认，所有需要批准的工具调用都会自动通过。如果你的提示词会让 Kimi 执行写文件、改代码等操作，它会直接执行，请确保提示词是安全的。

另外注意：kimi 命令需要在你的 PATH 里可用（即已经安装 Kimi Code CLI 并且可以全局调用）。

"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def find_mp4_files(folder: Path, recursive: bool = False) -> list[Path]:
    """Return MP4 files in the folder, sorted by name."""
    if recursive:
        mp4s = list(folder.rglob("*.mp4"))
    else:
        mp4s = list(folder.glob("*.mp4"))
    return sorted(mp4s, key=lambda p: p.name.lower())


def build_prompt(video_path: Path, user_prompt: str) -> str:
    """Build the prompt sent to kimi -p."""
    # Use a <video> tag so Kimi can invoke ReadMediaFile on the path.
    # The absolute path avoids cwd ambiguity.
    return f"<video path=\"{video_path.resolve()}\"></video>\n\n{user_prompt}"


def run_kimi(prompt: str, dry_run: bool = False) -> int:
    """Run `kimi -p <prompt>` and return the exit code."""
    cmd = ["kimi", "-p", prompt]
    if dry_run:
        print("[dry-run] Would run:", " ".join(cmd))
        return 0

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=False, text=True)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run kimi -p sequentially for every MP4 in a folder.",
    )
    parser.add_argument("folder", type=Path, help="Folder containing MP4 files.")
    parser.add_argument("prompt", help="Prompt text to append for each video.")
    parser.add_argument(
        "-r", "--recursive", action="store_true", help="Search recursively for MP4 files."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be executed without running kimi.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop if any kimi invocation returns a non-zero exit code.",
    )
    args = parser.parse_args()

    folder: Path = args.folder
    if not folder.exists():
        print(f"Error: folder not found: {folder}", file=sys.stderr)
        return 1
    if not folder.is_dir():
        print(f"Error: not a directory: {folder}", file=sys.stderr)
        return 1

    mp4s = find_mp4_files(folder, recursive=args.recursive)
    if not mp4s:
        print(f"No MP4 files found in: {folder}")
        return 0

    print(f"Found {len(mp4s)} MP4 file(s) in {folder}")
    if args.recursive:
        print("(recursive search enabled)")
    print()

    failed: list[Path] = []
    for idx, video_path in enumerate(mp4s, start=1):
        print(f"[{idx}/{len(mp4s)}] Processing: {video_path}")
        prompt = build_prompt(video_path, args.prompt)
        exit_code = run_kimi(prompt, dry_run=args.dry_run)

        if exit_code != 0:
            print(
                f"Warning: kimi exited with code {exit_code} for {video_path}",
                file=sys.stderr,
            )
            failed.append(video_path)
            if args.stop_on_error:
                print("Stopping due to --stop-on-error.", file=sys.stderr)
                return exit_code
        print()

    print(f"Done. Processed {len(mp4s)} file(s), {len(failed)} failed.")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
