from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

@dataclass
class Frame:
    number: int
    path: Path
    timestamp: float
    score: float

class VideoProcessor:
    # Class constants
    FRAME_DIFFERENCE_THRESHOLD = 10.0
    
    def __init__(self, video_path: Path, output_dir: Path, model: str):
        self.video_path = video_path
        self.output_dir = output_dir
        self.model = model
        self.frames: List[Frame] = []
        
    def _calculate_frame_difference(self, frame1: np.ndarray, frame2: np.ndarray) -> float:
        """Calculate the difference between two frames using absolute difference."""
        if frame1 is None or frame2 is None:
            return 0.0
        
        # Convert to grayscale for simpler comparison
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
        
        # Calculate absolute difference and mean
        diff = cv2.absdiff(gray1, gray2)
        score = np.mean(diff)
        
        return float(score)

    def _is_keyframe(self, current_frame: np.ndarray, prev_frame: np.ndarray, threshold: float = FRAME_DIFFERENCE_THRESHOLD) -> bool:
        """Determine if frame is significantly different from previous frame."""
        if prev_frame is None:
            return True
            
        score = self._calculate_frame_difference(current_frame, prev_frame)
        return score > threshold

    def extract_keyframes(self, frames_per_minute: int = 10, duration: Optional[float] = None, max_frames: Optional[int] = None) -> List[Frame]:
        """Extract keyframes from video targeting a specific number of frames per minute."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {self.video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_duration = total_frames / fps

        if duration:
            video_duration = min(duration, video_duration)
            total_frames = int(min(total_frames, duration * fps))

        logger.info(f"Video info: {self.video_path.name}, {video_duration:.1f}s, {fps:.1f} fps, {total_frames} frames total, resolution {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
        
        # Calculate target number of frames
        target_frames = max(1, min(
            int((video_duration / 60) * frames_per_minute),
            total_frames,
            max_frames if max_frames is not None else float('inf')
        ))
        
        # Calculate adaptive sampling interval
        sample_interval = max(1, total_frames // (target_frames * 2))
        
        frame_candidates = []
        prev_frame = None
        frame_count = 0
        report_interval = max(1, total_frames // 20)  # Report progress ~20 times

        logger.info(f"Scanning for keyframes (target: {target_frames}, sample interval: {sample_interval})...")
        while frame_count < total_frames:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_count % sample_interval == 0:
                score = self._calculate_frame_difference(frame, prev_frame)
                if score > self.FRAME_DIFFERENCE_THRESHOLD:
                    frame_candidates.append((frame_count, frame, score))
                prev_frame = frame.copy()

            frame_count += 1
            if frame_count % report_interval == 0:
                progress_pct = (frame_count / total_frames) * 100
                logger.info(f"  Frame scan: {frame_count}/{total_frames} ({progress_pct:.0f}%) — {len(frame_candidates)} candidates found")

        cap.release()
        logger.info(f"Keyframe scanning complete: {len(frame_candidates)} candidates, selecting top {target_frames}...")
        
        # Select the most significant frames by score, then restore chronological order
        selected_candidates = sorted(frame_candidates, key=lambda x: x[2], reverse=True)[:target_frames]

        # If max_frames is specified, sample evenly across the candidates
        if max_frames is not None and max_frames < len(selected_candidates):
            step = len(selected_candidates) / max_frames
            selected_frames = [selected_candidates[int(i * step)] for i in range(max_frames)]
        else:
            selected_frames = selected_candidates

        # Re-sort by frame number so frames on disk and in the JSON are chronological
        selected_frames = sorted(selected_frames, key=lambda x: x[0])

        self.frames = []
        total_selected = len(selected_frames)
        logger.info(f"Saving {total_selected} selected frames to disk...")
        for idx, (frame_num, frame, score) in enumerate(selected_frames):
            frame_path = self.output_dir / f"frame_{idx}.jpg"
            cv2.imwrite(str(frame_path), frame)
            timestamp = frame_num / fps
            self.frames.append(Frame(idx, frame_path, timestamp, score))
            if (idx + 1) % max(1, total_selected // 10) == 0 or idx == total_selected - 1:
                logger.info(f"  Saved frame {idx + 1}/{total_selected} @ {timestamp:.2f}s")

        logger.info(f"Extracted {len(self.frames)} frames from video (target was {target_frames})")
        return self.frames
