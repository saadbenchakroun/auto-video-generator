"""
Caption Burner - Burn SRT subtitles onto videos with custom styling
Uses FFmpeg and Pillow for advanced text rendering with custom fonts
"""

import subprocess
import re
import os
from pathlib import Path
from typing import Tuple, List, Optional, Dict
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont
import tempfile
import shutil


@dataclass
class CaptionStyle:
    """Style configuration for captions"""
    font_path: str = None  # Path to .ttf font file (None = default)
    font_size: int = 48
    font_color: Tuple[int, int, int] = (255, 255, 255)  # RGB white
    outline_color: Tuple[int, int, int] = (0, 0, 0)  # RGB black
    outline_width: int = 3
    background_color: Optional[Tuple[int, int, int, int]] = None  # RGBA (None = transparent)
    background_padding: int = 20
    position: str = "bottom"  # "top", "middle", "bottom"
    margin: int = 50  # Distance from edge
    shadow: bool = True
    shadow_offset: Tuple[int, int] = (3, 3)
    shadow_color: Tuple[int, int, int, int] = (0, 0, 0, 128)  # RGBA with alpha
    max_width: int = 1800  # Maximum text width before wrapping


@dataclass
class SubtitleEntry:
    """Single subtitle entry"""
    index: int
    start_time: float  # in seconds
    end_time: float  # in seconds
    text: str


class CaptionBurner:
    """Burns SRT subtitles onto videos with custom styling using Pillow and FFmpeg"""
    
    def __init__(self):
        self.temp_dir = None
    
    def parse_srt(self, srt_path: str) -> List[SubtitleEntry]:
        """Parse SRT file into subtitle entries"""
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split by double newlines (subtitle blocks)
        blocks = re.split(r'\n\s*\n', content.strip())
        
        subtitles = []
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue
            
            try:
                index = int(lines[0])
                time_line = lines[1]
                text = '\n'.join(lines[2:])
                
                # Parse timestamp: 00:00:01,500 --> 00:00:04,000
                match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})', time_line)
                if match:
                    h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, match.groups())
                    start_time = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
                    end_time = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
                    
                    subtitles.append(SubtitleEntry(index, start_time, end_time, text))
            except (ValueError, IndexError):
                continue
        
        return subtitles
    
    def _get_font(self, style: CaptionStyle) -> ImageFont.FreeTypeFont:
        """Load font from path or use default"""
        if style.font_path and os.path.exists(style.font_path):
            try:
                return ImageFont.truetype(style.font_path, style.font_size)
            except Exception as e:
                print(f"Warning: Could not load font {style.font_path}: {e}")
                print("Falling back to default font")
        
        # Try to use a default system font
        try:
            # Windows
            if os.name == 'nt':
                return ImageFont.truetype("C:/Windows/Fonts/arial.ttf", style.font_size)
            # Linux
            elif os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
                return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", style.font_size)
            # Mac
            elif os.path.exists("/System/Library/Fonts/Helvetica.ttc"):
                return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", style.font_size)
        except:
            pass
        
        # Fall back to PIL default
        return ImageFont.load_default()
    
    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
        """Wrap text to fit within max_width"""
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = font.getbbox(test_line)
            width = bbox[2] - bbox[0]
            
            if width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines if lines else [text]
    
    def _draw_text_with_outline(
        self, 
        draw: ImageDraw.Draw, 
        position: Tuple[int, int], 
        text: str, 
        font: ImageFont.FreeTypeFont,
        fill_color: Tuple[int, int, int],
        outline_color: Tuple[int, int, int],
        outline_width: int
    ):
        """Draw text with outline effect"""
        x, y = position
        
        # Draw outline by drawing text in all directions
        for offset_x in range(-outline_width, outline_width + 1):
            for offset_y in range(-outline_width, outline_width + 1):
                if offset_x != 0 or offset_y != 0:
                    draw.text((x + offset_x, y + offset_y), text, font=font, fill=outline_color)
        
        # Draw main text
        draw.text((x, y), text, font=font, fill=fill_color)
    
    def create_caption_image(
        self, 
        text: str, 
        video_width: int, 
        video_height: int, 
        style: CaptionStyle
    ) -> Image.Image:
        """Create a transparent PNG with styled caption text"""
        font = self._get_font(style)
        
        # Wrap text
        lines = self._wrap_text(text, font, style.max_width)
        
        # Calculate text dimensions
        line_heights = []
        line_widths = []
        for line in lines:
            bbox = font.getbbox(line)
            line_widths.append(bbox[2] - bbox[0])
            line_heights.append(bbox[3] - bbox[1])
        
        max_line_width = max(line_widths) if line_widths else 0
        total_height = sum(line_heights) + (len(lines) - 1) * 10  # 10px spacing between lines
        
        # Add padding for outline and shadow
        padding = style.outline_width * 2 + (style.shadow_offset[0] if style.shadow else 0) + 10
        img_width = max_line_width + padding * 2 + style.background_padding * 2
        img_height = total_height + padding * 2 + style.background_padding * 2
        
        # Create transparent image
        img = Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Draw background if specified
        if style.background_color:
            bg_rect = [
                style.background_padding,
                style.background_padding,
                img_width - style.background_padding,
                img_height - style.background_padding
            ]
            draw.rectangle(bg_rect, fill=style.background_color)
        
        # Calculate starting Y position for vertically centered text
        text_y = padding + style.background_padding
        
        # Draw each line
        for i, line in enumerate(lines):
            line_width = line_widths[i]
            line_height = line_heights[i]
            
            # Center horizontally
            text_x = (img_width - line_width) // 2
            
            # Draw shadow if enabled
            if style.shadow:
                shadow_x = text_x + style.shadow_offset[0]
                shadow_y = text_y + style.shadow_offset[1]
                
                # Create shadow layer
                for offset_x in range(-style.outline_width, style.outline_width + 1):
                    for offset_y in range(-style.outline_width, style.outline_width + 1):
                        draw.text(
                            (shadow_x + offset_x, shadow_y + offset_y), 
                            line, 
                            font=font, 
                            fill=style.shadow_color
                        )
            
            # Draw text with outline
            self._draw_text_with_outline(
                draw, 
                (text_x, text_y), 
                line, 
                font,
                style.font_color,
                style.outline_color,
                style.outline_width
            )
            
            text_y += line_height + 10  # Move down for next line
        
        return img
    
    def burn_captions(
        self, 
        video_path: str, 
        srt_path: str, 
        output_path: str,
        style: CaptionStyle = None,
        codec: str = 'libx264',
        crf: int = 18,
        preset: str = 'medium'
    ) -> str:
        """
        Burn SRT captions onto video with custom styling.
        
        Args:
            video_path: Input video file path
            srt_path: SRT subtitle file path
            output_path: Output video file path
            style: CaptionStyle object (None = default style)
            codec: Video codec (default: 'libx264')
            crf: Quality (0-51, lower = better, default: 18)
            preset: Encoding speed (ultrafast, fast, medium, slow, veryslow)
        
        Returns:
            Path to output video
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")
        if not os.path.exists(srt_path):
            raise FileNotFoundError(f"SRT not found: {srt_path}")
        
        style = style or CaptionStyle()
        
        # Get video dimensions
        video_info = self._get_video_info(video_path)
        video_width = video_info['width']
        video_height = video_info['height']
        fps = video_info['fps']
        
        print(f"Video: {video_width}x{video_height} @ {fps} fps")
        
        # Parse subtitles
        subtitles = self.parse_srt(srt_path)
        print(f"Found {len(subtitles)} subtitle entries")
        
        # Create temp directory for caption images
        self.temp_dir = tempfile.mkdtemp()
        print(f"Working directory: {self.temp_dir}")
        
        try:
            # Generate caption images
            print("Generating caption images...")
            caption_files = []
            
            for sub in subtitles:
                img = self.create_caption_image(sub.text, video_width, video_height, style)
                
                # Calculate position
                img_x = (video_width - img.width) // 2
                if style.position == "top":
                    img_y = style.margin
                elif style.position == "middle":
                    img_y = (video_height - img.height) // 2
                else:  # bottom
                    img_y = video_height - img.height - style.margin
                
                # Save image
                img_path = os.path.join(self.temp_dir, f"caption_{sub.index:04d}.png")
                img.save(img_path, 'PNG')
                
                caption_files.append({
                    'path': img_path,
                    'start': sub.start_time,
                    'end': sub.end_time,
                    'x': img_x,
                    'y': img_y
                })
            
            print(f"Generated {len(caption_files)} caption images")
            
            # Build FFmpeg filter complex for overlaying captions
            print("Building FFmpeg filter...")
            filter_parts = []
            current_input = "[0:v]"
            
            for i, caption in enumerate(caption_files):
                overlay_filter = (
                    f"{current_input}[{i+1}:v]overlay="
                    f"x={caption['x']}:y={caption['y']}:"
                    f"enable='between(t,{caption['start']},{caption['end']})'"
                )
                
                if i < len(caption_files) - 1:
                    overlay_filter += f"[v{i}]"
                    current_input = f"[v{i}]"
                else:
                    overlay_filter += "[outv]"
                
                filter_parts.append(overlay_filter)
            
            filter_complex = ';'.join(filter_parts)
            
            # Build FFmpeg command
            print("Encoding video with captions...")
            cmd = ['ffmpeg', '-i', video_path]
            
            # Add caption images as inputs
            for caption in caption_files:
                cmd.extend(['-loop', '1', '-i', caption['path']])
            
            # Add filter complex
            cmd.extend([
                '-filter_complex', filter_complex,
                '-map', '[outv]',
                '-map', '0:a?',  # Copy audio if exists
                '-c:v', codec,
                '-crf', str(crf),
                '-preset', preset,
                '-c:a', 'copy',  # Copy audio without re-encoding
                '-shortest',  # End when video ends
                '-y',  # Overwrite output
                output_path
            ])
            
            # Run FFmpeg
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg failed: {result.stderr}")
            
            print(f"✅ Success! Output: {output_path}")
            return output_path
            
        finally:
            # Cleanup temp directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                print("Cleaned up temporary files")
    
    def _get_video_info(self, video_path: str) -> Dict:
        """Get video dimensions and fps using ffprobe"""
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,r_frame_rate',
            '-of', 'default=noprint_wrappers=1',
            video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")
        
        lines = result.stdout.strip().split('\n')
        info = {}
        
        for line in lines:
            if '=' in line:
                key, value = line.split('=')
                if key == 'width':
                    info['width'] = int(value)
                elif key == 'height':
                    info['height'] = int(value)
                elif key == 'r_frame_rate':
                    # Parse fraction like "30/1"
                    num, den = map(int, value.split('/'))
                    info['fps'] = num / den
        
        return info


# Example usage
if __name__ == "__main__":
    burner = CaptionBurner()
    
    # Example 1: Basic usage with default style
    try:
        burner.burn_captions(
            video_path="input_video.mp4",
            srt_path="subtitles.srt",
            output_path="output_with_captions.mp4"
        )
    except Exception as e:
        print(f"Error: {e}")
    
    # Example 2: Custom style with local font
    custom_style = CaptionStyle(
        font_path="C:/Windows/Fonts/impact.ttf",  # Use Impact font on Windows
        font_size=52,
        font_color=(255, 255, 255),  # White
        outline_color=(0, 0, 0),  # Black outline
        outline_width=4,
        background_color=(0, 0, 0, 180),  # Semi-transparent black background
        background_padding=15,
        position="bottom",
        margin=60,
        shadow=True,
        shadow_offset=(4, 4),
        shadow_color=(0, 0, 0, 200),
        max_width=1600
    )
    
    try:
        burner.burn_captions(
            video_path="input_video.mp4",
            srt_path="subtitles.srt",
            output_path="output_custom_style.mp4",
            style=custom_style,
            crf=20  # Higher quality
        )
    except Exception as e:
        print(f"Error: {e}")
    
    # Example 3: Yellow text with heavy outline (YouTube style)
    youtube_style = CaptionStyle(
        font_path="C:/Windows/Fonts/arialbd.ttf",  # Arial Bold
        font_size=56,
        font_color=(255, 255, 0),  # Yellow
        outline_color=(0, 0, 0),  # Black
        outline_width=5,
        background_color=None,  # No background
        position="bottom",
        margin=80,
        shadow=True,
        shadow_offset=(5, 5),
        max_width=1700
    )
    
    try:
        burner.burn_captions(
            video_path="input_video.mp4",
            srt_path="subtitles.srt",
            output_path="output_youtube_style.mp4",
            style=youtube_style
        )
    except Exception as e:
        print(f"Error: {e}")