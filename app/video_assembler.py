"""
Video Assembler with Voice (FFmpeg-based)
A tool to stitch multiple videos together and add voice-over with volume control.
Handles old OpenCV encodings and outputs in libx264 format.

Requirements:
- FFmpeg must be installed on your system
- pip install ffmpeg-python
"""

import ffmpeg
from typing import List, Literal
import os
import subprocess
import json


class VideoAssembler:
    """Assembles multiple videos and adds voice-over with flexible duration control using FFmpeg."""
    
    def __init__(self):
        self.temp_files = []
    
    def _get_video_duration(self, video_path: str) -> float:
        """Get duration of a video file in seconds."""
        probe = ffmpeg.probe(video_path)
        duration = float(probe['streams'][0]['duration'])
        return duration
    
    def _get_audio_duration(self, audio_path: str) -> float:
        """Get duration of an audio file in seconds."""
        probe = ffmpeg.probe(audio_path)
        for stream in probe['streams']:
            if stream['codec_type'] == 'audio':
                return float(stream['duration'])
        raise ValueError("No audio stream found in file")
    
    def stitch_videos(self, video_paths: List[str], output_path: str, 
                      codec: str = 'libx264', crf: int = 23, preset: str = 'medium') -> str:
        """
        Stitch multiple videos together into a single video with libx264 encoding.
        
        Args:
            video_paths: List of paths to video files
            output_path: Path for the output video
            codec: Video codec (default: 'libx264')
            crf: Constant Rate Factor for quality (0-51, lower is better, default: 23)
            preset: Encoding preset (ultrafast, fast, medium, slow, veryslow)
        
        Returns:
            Path to the stitched video
        """
        if not video_paths:
            raise ValueError("No video paths provided")
        
        # Verify all files exist
        for path in video_paths:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Video file not found: {path}")
        
        # Create a temporary file list for FFmpeg concat
        concat_file = "concat_list.txt"
        with open(concat_file, 'w') as f:
            for path in video_paths:
                # Convert to absolute path and escape special characters
                abs_path = os.path.abspath(path)
                f.write(f"file '{abs_path}'\n")
        
        self.temp_files.append(concat_file)
        
        # Stitch videos using FFmpeg concat demuxer with re-encoding to libx264
        try:
            (
                ffmpeg
                .input(concat_file, format='concat', safe=0)
                .output(output_path, 
                       vcodec=codec,
                       crf=crf,
                       preset=preset,
                       acodec='aac',
                       audio_bitrate='192k')
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            
            duration = self._get_video_duration(output_path)
            print(f"✓ Stitched {len(video_paths)} videos. Total duration: {duration:.2f}s")
            print(f"✓ Output: {output_path} (codec: {codec})")
            return output_path
            
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise RuntimeError(f"FFmpeg error during stitching: {error_msg}")
    
    def add_voice(self,
                  video_path: str,
                  audio_path: str,
                  output_path: str,
                  volume: float = 1.0,
                  duration_mode: Literal["video", "audio"] = "video",
                  start_time: float = 0.0,
                  fade_in: float = 0.0,
                  fade_out: float = 0.0,
                  codec: str = 'libx264',
                  crf: int = 23) -> str:
        """
        Add voice-over to video with volume control and duration options.
        
        Args:
            video_path: Path to input video
            audio_path: Path to audio file
            output_path: Path for output video
            volume: Volume multiplier (0.0 to 2.0, default: 1.0)
            duration_mode: "video" = match video length, "audio" = match audio length
            start_time: When to start audio in video (seconds)
            fade_in: Audio fade in duration (seconds)
            fade_out: Audio fade out duration (seconds)
            codec: Video codec (default: 'libx264')
            crf: Constant Rate Factor for quality (default: 23)
        
        Returns:
            Path to the output video with voice-over
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        video_duration = self._get_video_duration(video_path)
        audio_duration = self._get_audio_duration(audio_path)
        
        # Prepare audio stream with volume control
        audio = ffmpeg.input(audio_path)
        
        # Build audio filter chain
        audio_filters = []
        
        # Volume adjustment
        if volume != 1.0:
            audio_filters.append(f'volume={volume}')
        
        # Fade in/out
        if fade_in > 0:
            audio_filters.append(f'afade=t=in:st=0:d={fade_in}')
        if fade_out > 0:
            fade_start = audio_duration - fade_out
            audio_filters.append(f'afade=t=out:st={fade_start}:d={fade_out}')
        
        # Delay audio if start_time is specified
        if start_time > 0:
            audio_filters.append(f'adelay={int(start_time * 1000)}|{int(start_time * 1000)}')
        
        # Apply audio filters
        if audio_filters:
            audio = audio.filter('aformat', channel_layouts='stereo').filter_multi_output(
                ','.join(audio_filters)
            )
        
        # Load video
        video = ffmpeg.input(video_path)
        
        # Determine final duration
        if duration_mode == "video":
            # Trim or loop audio to match video duration
            if audio_duration < video_duration:
                # Loop audio if it's shorter
                loops = int(video_duration / audio_duration) + 1
                audio = audio.filter('aloop', loop=loops, size=int(audio_duration * 48000))
            # Trim to video duration
            audio = audio.filter('atrim', duration=video_duration)
            output_duration = None  # Use video duration
        else:  # duration_mode == "audio"
            # Extend or trim video to match audio duration
            if video_duration < audio_duration + start_time:
                # Loop video if needed
                video = video.filter('loop', loop=-1, size=1)
            output_duration = audio_duration + start_time
        
        # Merge video and audio
        try:
            output_args = {
                'vcodec': codec,
                'crf': crf,
                'preset': 'medium',
                'acodec': 'aac',
                'audio_bitrate': '192k'
            }
            
            if output_duration:
                output_args['t'] = output_duration
            
            (
                ffmpeg
                .output(video, audio, output_path, **output_args)
                .overwrite_output()
                .run()
                #.run(capture_stdout=True, capture_stderr=True)
            )
            
            print(f"✓ Added voice to video")
            print(f"  Video duration: {video_duration:.2f}s")
            print(f"  Audio duration: {audio_duration:.2f}s")
            print(f"  Mode: {duration_mode}")
            print(f"  Output: {output_path}")
            return output_path
            
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise RuntimeError(f"FFmpeg error during audio addition: {error_msg}")
    
    def merge_audio_tracks(self,
                          video_path: str,
                          audio_paths: List[str],
                          output_path: str,
                          volumes: List[float] = None,
                          codec: str = 'libx264',
                          crf: int = 23) -> str:
        """
        Merge multiple audio tracks with the video.
        
        Args:
            video_path: Path to input video
            audio_paths: List of audio file paths
            output_path: Path for output video
            volumes: List of volume multipliers for each audio track
            codec: Video codec (default: 'libx264')
            crf: Constant Rate Factor for quality
        
        Returns:
            Path to the output video
        """
        if not audio_paths:
            raise ValueError("No audio paths provided")
        
        if volumes and len(volumes) != len(audio_paths):
            raise ValueError("Number of volumes must match number of audio paths")
        
        if not volumes:
            volumes = [1.0] * len(audio_paths)
        
        # Load video
        video = ffmpeg.input(video_path)
        
        # Load and process audio tracks
        audio_streams = []
        for i, (audio_path, vol) in enumerate(zip(audio_paths, volumes)):
            audio = ffmpeg.input(audio_path)
            if vol != 1.0:
                audio = audio.filter('volume', vol)
            audio_streams.append(audio)
        
        # Mix all audio streams
        if len(audio_streams) > 1:
            mixed_audio = ffmpeg.filter(audio_streams, 'amix', inputs=len(audio_streams))
        else:
            mixed_audio = audio_streams[0]
        
        # Output with merged audio
        try:
            (
                ffmpeg
                .output(video, mixed_audio, output_path,
                       vcodec=codec,
                       crf=crf,
                       preset='medium',
                       acodec='aac',
                       audio_bitrate='192k')
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            
            print(f"✓ Merged {len(audio_paths)} audio tracks")
            print(f"  Output: {output_path}")
            return output_path
            
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise RuntimeError(f"FFmpeg error during audio merge: {error_msg}")
    
    def cleanup_temp_files(self):
        """Remove temporary files created during processing."""
        for temp_file in self.temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)
                print(f"✓ Cleaned up: {temp_file}")
        self.temp_files = []


# Example usage
if __name__ == "__main__":
    assembler = VideoAssembler()
    
    # # Example 1: Stitch videos together
    # try:
    #     video_files = ['video1.mp4', 'video2.mp4', 'video3.mp4']
    #     stitched = assembler.stitch_videos(
    #         video_paths=video_files,
    #         output_path='stitched_output.mp4',
    #         crf=20  # Higher quality
    #     )
    # except Exception as e:
    #     print(f"Error stitching videos: {e}")
    
    # Example 2: Add voice-over (match video duration)
    # try:
    #     with_voice = assembler.add_voice(
    #         video_path='stitched_output.mp4',
    #         audio_path='voiceover.mp3',
    #         output_path='final_with_voice.mp4',
    #         volume=1.2,
    #         duration_mode='video',  # Match video length
    #         fade_in=0.5,
    #         fade_out=1.0
    #     )
    # except Exception as e:
    #     print(f"Error adding voice: {e}")
    
    # # Example 3: Add voice-over (match audio duration)
    # try:
    #     with_voice = assembler.add_voice(
    #         video_path='video.mp4',
    #         audio_path='long_voiceover.mp3',
    #         output_path='extended_video.mp4',
    #         volume=1.0,
    #         duration_mode='audio',  # Extend video to match audio
    #         start_time=2.0  # Start audio 2 seconds into video
    #     )
    # except Exception as e:
    #     print(f"Error adding voice: {e}")
    
    # # Example 4: Merge multiple audio tracks
    # try:
    #     merged = assembler.merge_audio_tracks(
    #         video_path='video.mp4',
    #         audio_paths=['background_music.mp3', 'voiceover.mp3'],
    #         output_path='multi_audio_output.mp4',
    #         volumes=[0.3, 1.0]  # Background music quieter
    #     )
    # except Exception as e:
    #     print(f"Error merging audio: {e}")
    
    # # Cleanup
    # assembler.cleanup_temp_files()

    assembler.add_voice(
        video_path='temp_assets/stitched_temp.mp4',
        audio_path='temp_assets/voice_3.wav',
        output_path='result.mp4',
        volume=1.0,
        duration_mode='video',
    )
    assembler.add_voice(
        video_path='temp_assets/stitched_temp.mp4',
        audio_path='temp_assets/voice_3.wav',
        output_path='result2.mp4',
        volume=1.0,
        duration_mode='audio',
    )