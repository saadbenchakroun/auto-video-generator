from faster_whisper import WhisperModel
from dataclasses import dataclass
from typing import List, Tuple, Optional
from enum import Enum
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import gc


class GroupingStrategy(Enum):
    FIXED_WORD_COUNT = "fixed_word_count"
    TIME_BASED = "time_based"
    CHARACTER_COUNT = "character_count"
    SMART_PHRASE = "smart_phrase"


@dataclass
class SubtitleEntry:
    index: int
    start_time: float
    end_time: float
    text: str


@dataclass
class SRTConfig:
    # Grouping strategies
    grouping_strategy: GroupingStrategy = GroupingStrategy.FIXED_WORD_COUNT
    
    # Fixed word count strategy
    words_per_subtitle: int = 3
    
    # Time-based strategy (in seconds)
    max_duration_per_subtitle: float = 2.0
    
    # Character count strategy
    max_chars_per_subtitle: int = 42
    
    # Smart phrase strategy
    smart_phrase_min_words_for_minor_punct: int = 3
    smart_phrase_max_words: int = 5
    
    # Punctuation settings
    punctuation_marks: Tuple[str, ...] = ('.', '!', '?', ',', ';', ':')
    
    # Timing adjustments
    end_phrase_extension: float = 0.3
    min_gap_between_subtitles: float = 0.1
    
    # Whisper model settings
    model_path: str = "C:/faster-whisper-model/base.en"
    device: str = "cpu"
    compute_type: str = "int8"
    cpu_threads: int = 3
    num_workers: int = 1


class SRTGenerator:
    def __init__(self, config: SRTConfig = None):
        self.config = config or SRTConfig()
        self.model = None
        
    def load_model(self):
        if not self.model:
            self.model = WhisperModel(
                self.config.model_path,
                device=self.config.device,
                compute_type=self.config.compute_type,
                cpu_threads=self.config.cpu_threads,
                num_workers=self.config.num_workers
            )
    
    def unload_model(self):
        if self.model:
            del self.model
            self.model = None
            gc.collect()
    
    def transcribe_audio(self, audio_path: str) -> List[dict]:
        segments, _ = self.model.transcribe(audio_path, word_timestamps=True)
        
        all_words = []
        for segment in segments:
            for word in segment.words:
                if word.word.strip():
                    all_words.append({
                        'word': word.word.strip(),
                        'start': word.start,
                        'end': word.end
                    })
        
        return all_words
    
    def _prevent_overlaps(self, subtitles: List[SubtitleEntry]) -> List[SubtitleEntry]:
        """Ensure no subtitle overlaps with the next one"""
        for i in range(len(subtitles) - 1):
            next_start = subtitles[i + 1].start_time
            if subtitles[i].end_time + self.config.min_gap_between_subtitles > next_start:
                subtitles[i].end_time = next_start - self.config.min_gap_between_subtitles
        
        return subtitles
    
    def group_words_fixed_count(self, words: List[dict]) -> List[SubtitleEntry]:
        subtitles = []
        index = 1
        i = 0
        major_punctuation = ('.', '!', '?')
        
        while i < len(words):
            group_words = []
            group_start = words[i]['start']
            group_end = words[i]['end']
            
            for j in range(self.config.words_per_subtitle):
                if i + j >= len(words):
                    break
                
                current_word = words[i + j]
                group_words.append(current_word['word'])
                group_end = current_word['end']
                
                if any(current_word['word'].endswith(p) for p in self.config.punctuation_marks):
                    i += j + 1
                    break
            else:
                i += len(group_words)
            
            if group_words:
                is_phrase_end = any(group_words[-1].endswith(p) for p in major_punctuation)
                if is_phrase_end:
                    group_end += self.config.end_phrase_extension
                
                subtitles.append(SubtitleEntry(
                    index=index,
                    start_time=group_start,
                    end_time=group_end,
                    text=' '.join(group_words)
                ))
                index += 1
        
        return self._prevent_overlaps(subtitles)
    
    def group_words_time_based(self, words: List[dict]) -> List[SubtitleEntry]:
        subtitles = []
        index = 1
        i = 0
        major_punctuation = ('.', '!', '?')
        
        while i < len(words):
            group_words = []
            group_start = words[i]['start']
            group_end = words[i]['end']
            
            j = 0
            while i + j < len(words):
                current_word = words[i + j]
                potential_end = current_word['end']
                
                if potential_end - group_start > self.config.max_duration_per_subtitle and j > 0:
                    break
                
                group_words.append(current_word['word'])
                group_end = current_word['end']
                
                if any(current_word['word'].endswith(p) for p in self.config.punctuation_marks):
                    j += 1
                    break
                
                j += 1
            
            i += len(group_words) if group_words else 1
            
            if group_words:
                is_phrase_end = any(group_words[-1].endswith(p) for p in major_punctuation)
                if is_phrase_end:
                    group_end += self.config.end_phrase_extension
                
                subtitles.append(SubtitleEntry(
                    index=index,
                    start_time=group_start,
                    end_time=group_end,
                    text=' '.join(group_words)
                ))
                index += 1
        
        return self._prevent_overlaps(subtitles)
    
    def group_words_character_count(self, words: List[dict]) -> List[SubtitleEntry]:
        subtitles = []
        index = 1
        i = 0
        major_punctuation = ('.', '!', '?')
        
        while i < len(words):
            group_words = []
            group_start = words[i]['start']
            group_end = words[i]['end']
            
            j = 0
            while i + j < len(words):
                current_word = words[i + j]
                
                # Calculate potential text length
                potential_text = ' '.join(group_words + [current_word['word']])
                
                if len(potential_text) > self.config.max_chars_per_subtitle and j > 0:
                    break
                
                group_words.append(current_word['word'])
                group_end = current_word['end']
                
                if any(current_word['word'].endswith(p) for p in self.config.punctuation_marks):
                    j += 1
                    break
                
                j += 1
            
            i += len(group_words) if group_words else 1
            
            if group_words:
                is_phrase_end = any(group_words[-1].endswith(p) for p in major_punctuation)
                if is_phrase_end:
                    group_end += self.config.end_phrase_extension
                
                subtitles.append(SubtitleEntry(
                    index=index,
                    start_time=group_start,
                    end_time=group_end,
                    text=' '.join(group_words)
                ))
                index += 1
        
        return self._prevent_overlaps(subtitles)
    
    def group_words_smart_phrase(self, words: List[dict]) -> List[SubtitleEntry]:
        subtitles = []
        index = 1
        i = 0
        
        minor_punctuation = (',', ';', ':')
        major_punctuation = ('.', '!', '?')
        
        while i < len(words):
            group_words = []
            group_start = words[i]['start']
            group_end = words[i]['end']
            
            j = 0
            while i + j < len(words):
                current_word = words[i + j]
                group_words.append(current_word['word'])
                group_end = current_word['end']
                
                has_major_punct = any(current_word['word'].endswith(p) for p in major_punctuation)
                has_minor_punct = any(current_word['word'].endswith(p) for p in minor_punctuation)
                
                if has_major_punct:
                    j += 1
                    break
                elif has_minor_punct and len(group_words) >= self.config.smart_phrase_min_words_for_minor_punct:
                    j += 1
                    break
                elif len(group_words) >= self.config.smart_phrase_max_words:
                    j += 1
                    break
                
                j += 1
            
            i += len(group_words) if group_words else 1
            
            if group_words:
                is_phrase_end = any(group_words[-1].endswith(p) for p in major_punctuation)
                if is_phrase_end:
                    group_end += self.config.end_phrase_extension
                
                subtitles.append(SubtitleEntry(
                    index=index,
                    start_time=group_start,
                    end_time=group_end,
                    text=' '.join(group_words)
                ))
                index += 1
        
        return self._prevent_overlaps(subtitles)
    
    def group_words(self, words: List[dict]) -> List[SubtitleEntry]:
        if not words:
            return []
        
        if self.config.grouping_strategy == GroupingStrategy.FIXED_WORD_COUNT:
            return self.group_words_fixed_count(words)
        elif self.config.grouping_strategy == GroupingStrategy.TIME_BASED:
            return self.group_words_time_based(words)
        elif self.config.grouping_strategy == GroupingStrategy.CHARACTER_COUNT:
            return self.group_words_character_count(words)
        elif self.config.grouping_strategy == GroupingStrategy.SMART_PHRASE:
            return self.group_words_smart_phrase(words)
    
    def format_timestamp(self, seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds - int(seconds)) * 1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"
    
    def generate_srt_content(self, subtitles: List[SubtitleEntry]) -> str:
        if not subtitles:
            return ""
        
        srt_lines = []
        for subtitle in subtitles:
            start = self.format_timestamp(subtitle.start_time)
            end = self.format_timestamp(subtitle.end_time)
            srt_lines.append(f"{subtitle.index}\n{start} --> {end}\n{subtitle.text}\n")
        
        return '\n'.join(srt_lines)
    
    def generate_srt(self, audio_path: str, output_path: str) -> bool:
        """Generate single SRT file from audio"""
        words = self.transcribe_audio(audio_path)
        
        if not words:
            return False
        
        subtitles = self.group_words(words)
        
        if not subtitles:
            return False
        
        srt_content = self.generate_srt_content(subtitles)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
        
        return True
    
    def generate_multiple_srts(
        self, 
        audio_paths: List[str], 
        output_paths: Optional[List[str]] = None,
        max_workers: int = 2
    ) -> List[Tuple[str, bool]]:
        """
        Efficiently generate multiple SRT files from multiple audio files.
        
        Args:
            audio_paths: List of audio file paths
            output_paths: Optional list of output SRT paths (auto-generated if None)
            max_workers: Number of parallel workers for transcription
        
        Returns:
            List of tuples (audio_path, success_status)
        """
        # Load model once for all operations
        self.load_model()
        
        # Auto-generate output paths if not provided
        if output_paths is None:
            output_paths = [
                str(Path(audio).with_suffix('.srt')) 
                for audio in audio_paths
            ]
        
        results = []
        
        # Process transcriptions in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_audio = {
                executor.submit(self.transcribe_audio, audio_path): (audio_path, output_path)
                for audio_path, output_path in zip(audio_paths, output_paths)
            }
            
            for future in as_completed(future_to_audio):
                audio_path, output_path = future_to_audio[future]
                
                try:
                    words = future.result()
                    
                    if not words:
                        results.append((audio_path, False))
                        continue
                    
                    # Group words and generate SRT (fast, done serially)
                    subtitles = self.group_words(words)
                    
                    if not subtitles:
                        results.append((audio_path, False))
                        continue
                    
                    srt_content = self.generate_srt_content(subtitles)
                    
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(srt_content)
                    
                    results.append((audio_path, True))
                    
                except Exception as e:
                    results.append((audio_path, False))
        
        return results


# Usage examples:
if __name__ == "__main__":
    # Example 1: Single SRT generation
    config = SRTConfig(
        grouping_strategy=GroupingStrategy.FIXED_WORD_COUNT,
        words_per_subtitle=3,
        end_phrase_extension=0.3,
        model_path="C:/faster-whisper-model/base.en"
    )
    
    generator = SRTGenerator(config)
    generator.load_model()
    generator.generate_srt("audio.wav", "output.srt")
    generator.unload_model()
    
    # Example 2: Multiple SRTs generation (EFFICIENT)
    audio_files = [
        "audio1.wav",
        "audio2.wav",
        "audio3.wav"
    ]
    
    config = SRTConfig(
        grouping_strategy=GroupingStrategy.FIXED_WORD_COUNT,
        words_per_subtitle=4,
        end_phrase_extension=0.4,
        model_path="C:/faster-whisper-model/base.en"
    )
    
    generator = SRTGenerator(config)
    results = generator.generate_multiple_srts(audio_files, max_workers=2)
    generator.unload_model()
    
    for audio_path, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {audio_path}")