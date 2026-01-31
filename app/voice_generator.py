"""
VoiceGenerator - Streamlined text-to-speech using Kokoro TTS
Optimized for quick single and batch audio generation
"""

import os
import gc
import time
import logging
from pathlib import Path
from typing import Union, List, Optional
from dataclasses import dataclass

import torch
import soundfile as sf
import numpy as np
from kokoro import KPipeline

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """Result of audio generation"""
    success: bool
    output_path: Optional[str] = None
    duration: Optional[float] = None
    error: Optional[str] = None


class VoiceGenerator:
    """
    Fast text-to-speech generator using Kokoro TTS.
    
    Features:
    - Single text generation
    - Batch text generation (sequential)
    - Memory-efficient chunked processing
    - Automatic cleanup
    """
    
    MAX_TEXT_LENGTH = 50000  # characters
    
    def __init__(
        self,
        model_path: str,
        voice_path: str,
        sample_rate: int = 24000,
        lang_code: str = 'a',
        cpu_threads: int = 4
    ):
        """
        Initialize the VoiceGenerator.
        
        Args:
            model_path: Path to Kokoro model directory
            voice_path: Path to voice model file
            sample_rate: Audio sample rate (default: 24000)
            lang_code: Language code (default: 'a')
            cpu_threads: CPU threads to use (default: 4)
        
        Raises:
            ValueError: If paths are invalid
            FileNotFoundError: If model or voice files don't exist
        """
        # Initialize attributes FIRST (for __del__ safety)
        self.pipeline = None
        self._is_loaded = False
        
        # Validate inputs
        self._validate_init_params(model_path, voice_path, sample_rate, cpu_threads)
        
        self.model_path = model_path
        self.voice_path = voice_path
        self.sample_rate = sample_rate
        self.lang_code = lang_code
        self.cpu_threads = cpu_threads
        
        # Configure CPU
        self._configure_cpu()
        
        # Auto-load model
        self.load_model()
    
    def _validate_init_params(
        self,
        model_path: str,
        voice_path: str,
        sample_rate: int,
        cpu_threads: int
    ):
        """Validate initialization parameters"""
        if not model_path or not isinstance(model_path, str):
            raise ValueError("model_path must be a non-empty string")
        
        if not voice_path or not isinstance(voice_path, str):
            raise ValueError("voice_path must be a non-empty string")
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model path not found: {model_path}")
        
        if not os.path.exists(voice_path):
            raise FileNotFoundError(f"Voice path not found: {voice_path}")
        
        if sample_rate <= 0 or sample_rate > 48000:
            raise ValueError(f"Invalid sample_rate: {sample_rate}. Must be between 1-48000")
        
        if cpu_threads < 1 or cpu_threads > 32:
            raise ValueError(f"Invalid cpu_threads: {cpu_threads}. Must be between 1-32")
    
    def _configure_cpu(self):
        """Configure CPU threading"""
        torch.set_num_threads(self.cpu_threads)
        os.environ['OMP_NUM_THREADS'] = str(self.cpu_threads)
        os.environ['MKL_NUM_THREADS'] = str(self.cpu_threads)
    
    def load_model(self) -> bool:
        """
        Load the Kokoro TTS model.
        
        Returns:
            bool: True if successful
        
        Raises:
            RuntimeError: If model loading fails
        """
        if self._is_loaded:
            logger.warning("Model already loaded")
            return True
        
        try:
            logger.info("Loading Kokoro TTS model...")
            self.pipeline = KPipeline(
                lang_code=self.lang_code,
                repo_id=self.model_path
            )
            self._is_loaded = True
            logger.info("✓ Model loaded successfully")
            return True
        
        except Exception as e:
            error_msg = f"Failed to load model: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def unload_model(self):
        """Unload model and free memory"""
        if self.pipeline:
            del self.pipeline
            self.pipeline = None
            self._is_loaded = False
            gc.collect()
            logger.info("Model unloaded")
    
    def generate(
        self,
        text: str,
        output_path: str,
        overwrite: bool = True
    ) -> GenerationResult:
        """
        Generate audio from text.
        
        Args:
            text: Input text to convert to speech
            output_path: Output audio file path (must end with .wav)
            overwrite: Whether to overwrite existing files (default: True)
        
        Returns:
            GenerationResult with success status and details
        
        Raises:
            RuntimeError: If model not loaded
            ValueError: If inputs are invalid
        """
        # Validate
        self._validate_generate_params(text, output_path, overwrite)
        
        start_time = time.time()
        temp_path = output_path + ".tmp"
        
        try:
            # Ensure output directory exists
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            
            logger.info(f"Generating: {Path(output_path).name}")
            
            # Generate audio in chunks
            all_audio = []
            chunk_count = 0
            
            for _, _, audio in self.pipeline(text, voice=self.voice_path):
                all_audio.append(audio)
                chunk_count += 1
            
            # Combine and write
            if all_audio:
                combined_audio = np.concatenate(all_audio)
                sf.write(temp_path, combined_audio, self.sample_rate, format='WAV')
                
                # Move temp to final location
                if os.path.exists(output_path):
                    os.remove(output_path)
                os.rename(temp_path, output_path)
                
                del combined_audio
            else:
                raise RuntimeError("No audio generated from pipeline")
            
            duration = time.time() - start_time
            logger.info(f"✓ Generated in {duration:.2f}s ({chunk_count} chunks)")
            
            return GenerationResult(
                success=True,
                output_path=output_path,
                duration=duration
            )
        
        except Exception as e:
            error_msg = f"Generation failed: {e}"
            logger.error(error_msg)
            
            # Cleanup temp file
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            
            return GenerationResult(
                success=False,
                error=error_msg
            )
        
        finally:
            gc.collect()
    
    def _validate_generate_params(
        self,
        text: str,
        output_path: str,
        overwrite: bool
    ):
        """Validate generation parameters"""
        if not self._is_loaded:
            raise RuntimeError("Model not loaded. Initialization may have failed.")
        
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        
        if len(text) > self.MAX_TEXT_LENGTH:
            raise ValueError(
                f"Text too long ({len(text)} chars). Max: {self.MAX_TEXT_LENGTH}"
            )
        
        if not output_path:
            raise ValueError("output_path cannot be empty")
        
        # Validate file extension
        ext = Path(output_path).suffix.lower()
        if ext not in {'.wav'}:
            raise ValueError(
                f"Unsupported format: {ext}. Only .wav is supported"
            )
        
        # Check if file exists and overwrite is disabled
        if os.path.exists(output_path) and not overwrite:
            raise FileExistsError(
                f"File exists and overwrite=False: {output_path}"
            )
        
        # Validate path is writable (check parent dir exists and is writable)
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            # Directory will be created, just check parent is writable
            parent = os.path.dirname(output_dir) or '.'
            if os.path.exists(parent) and not os.access(parent, os.W_OK):
                raise PermissionError(f"Cannot write to directory: {parent}")
        elif output_dir and not os.access(output_dir, os.W_OK):
            raise PermissionError(f"Cannot write to directory: {output_dir}")
        elif not output_dir:
            # Writing to current directory
            if not os.access('.', os.W_OK):
                raise PermissionError("Cannot write to current directory")
    
    def generate_batch(
        self,
        texts: Union[List[str], dict],
        output_dir: str,
        prefix: str = "audio",
        overwrite: bool = True
    ) -> dict:
        """
        Generate audio for multiple texts.
        
        Args:
            texts: List of strings OR dict of {name: text}
            output_dir: Output directory for audio files
            prefix: Filename prefix if texts is a list (default: "audio")
            overwrite: Whether to overwrite existing files (default: True)
        
        Returns:
            Dict mapping filename to GenerationResult
        
        Raises:
            ValueError: If texts is empty or invalid
        """
        if not texts:
            raise ValueError("texts cannot be empty")
        
        # Convert list to dict
        if isinstance(texts, list):
            text_dict = {f"{prefix}_{i+1:03d}": text for i, text in enumerate(texts)}
        elif isinstance(texts, dict):
            text_dict = texts
        else:
            raise ValueError("texts must be a list or dict")
        
        os.makedirs(output_dir, exist_ok=True)
        
        logger.info(f"Batch processing {len(text_dict)} texts...")
        
        results = {}
        for idx, (name, text) in enumerate(text_dict.items(), 1):
            output_path = os.path.join(output_dir, f"{name}.wav")
            
            logger.info(f"[{idx}/{len(text_dict)}] Processing: {name}")
            
            try:
                result = self.generate(text, output_path, overwrite)
                results[name] = result
            except Exception as e:
                logger.error(f"Failed to process {name}: {e}")
                results[name] = GenerationResult(
                    success=False,
                    error=str(e)
                )
        
        # Summary
        successful = sum(1 for r in results.values() if r.success)
        logger.info(f"Batch complete: {successful}/{len(results)} successful")
        
        return results
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.unload_model()
    
    def __del__(self):
        """Cleanup on deletion"""
        try:
            if hasattr(self, '_is_loaded') and self._is_loaded:
                self.unload_model()
        except Exception:
            pass  # Ignore errors during cleanup


# ==================== USAGE EXAMPLES ====================

def example_single():
    """Generate a single audio file"""
    # UPDATE THESE PATHS TO MATCH YOUR SETUP!
    generator = VoiceGenerator(
        model_path="path/to/your/kokoro_model",
        voice_path="path/to/your/kokoro_model/voices/voice_file"
    )
    
    text = "Hello, this is a test of the voice generation system."
    result = generator.generate(text, "output/test.wav")
    
    print(f"Success: {result.success}")
    if result.success:
        print(f"Duration: {result.duration:.2f}s")


def example_batch():
    """Generate multiple audio files"""
    # UPDATE THESE PATHS TO MATCH YOUR SETUP!
    with VoiceGenerator(
        model_path="path/to/your/kokoro_model",
        voice_path="path/to/your/kokoro_model/voices/voice_file"
    ) as generator:
        
        texts = [
            "First sample.",
            "Second sample.",
            "Third sample."
        ]
        
        results = generator.generate_batch(texts, "output/batch")
        
        # Check results
        for name, result in results.items():
            if result.success:
                print(f"✓ {name}: {result.duration:.2f}s")
            else:
                print(f"✗ {name}: {result.error}")


def example_batch_named():
    """Generate batch with custom names"""
    # UPDATE THESE PATHS TO MATCH YOUR SETUP!
    with VoiceGenerator(
        model_path="C:/kokoro_model",
        voice_path="C:/kokoro_model/voices/am_michael.pt"
    ) as generator:
        
        texts = {
            "intro": """Welcome to the first line.
            This is the first line break.
            and this is the second line break.
            now let's check for the pauses and quality""",
            "main": "Here is the main content.",
            "outro": "Thank you for listening."
        }
        
        results = generator.generate_batch(texts, "output/named")


if __name__ == "__main__":
    print("VoiceGenerator - Ready to use!")
    print("\nIMPORTANT: Update the paths in the example functions to match your setup!")
    print("\nUsage examples:")
    print("  example_single()      - Generate one file")
    print("  example_batch()       - Generate multiple files")
    print("  example_batch_named() - Generate batch with custom names")
    print("\n⚠️  Don't run examples until you update the file paths!")
    example_batch_named()