import requests
import json
import random
import time
import threading
import logging
from pathlib import Path
from typing import List, Optional, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImageGenerationError(Exception):
    """Raised for errors during the AI image generation process."""
    pass

class ImageGenerator:
    """
    Client for Cloudflare Workers AI API with robust error handling, rate limiting,
    and fallback to black images.
    """
    def __init__(self,
                 account_id: str,
                 api_token: str,
                 output_dir: str = "temp_assets",
                 width: int = 1280,
                 height: int = 720,
                 num_steps: int = 20):
        
        if not account_id or not api_token:
            raise ValueError("Cloudflare account ID and API token are required.")
            
        self.account_id = account_id
        self.api_token = api_token
        self.width = width
        self.height = height
        self.num_steps = num_steps
        self.output_path = Path(output_dir)
        
        # Rate limiting
        self._request_times = []
        self._lock = threading.Lock()
        
        self.base_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/stabilityai/stable-diffusion-xl-base-1.0"
        self.output_path.mkdir(parents=True, exist_ok=True)

    def _wait_for_rate_limit(self, requests_per_minute: int = 100):
        with self._lock:
            current_time = time.time()
            self._request_times = [t for t in self._request_times if current_time - t < 60]
            if len(self._request_times) >= requests_per_minute:
                wait_time = 60 - (current_time - self._request_times[0]) + 0.1
                logger.info(f"Rate limit reached, waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
            self._request_times.append(time.time())

    def _make_api_request(self, payload: dict) -> bytes:
        self._wait_for_rate_limit()
        try:
            response = requests.post(
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=120
            )
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            raise ImageGenerationError(f"Cloudflare API error: {e}") from e

    def _save_image_data(self, image_data: bytes, filename: str) -> Path:
        try:
            file_path = self.output_path / filename
            with open(file_path, "wb") as f:
                f.write(image_data)
            return file_path
        except Exception as e:
            raise ImageGenerationError(f"Failed to save image {filename}: {e}") from e

    def _create_fallback_image(self, filename: str) -> Path:
        """Creates a black image as fallback."""
        try:
            file_path = self.output_path / filename
            img = Image.new('RGB', (self.width, self.height), color='black')
            img.save(file_path)
            logger.warning(f"Created fallback black image for {filename}")
            return file_path
        except Exception as e:
            logger.error(f"Failed to create fallback image: {e}")
            raise

    def generate_image(self, prompt: str, filename: str, negative_prompt: Optional[str] = None, seed: Optional[int] = None) -> Path:
        logger.info(f"Generatng: {filename}")
        payload = {"prompt": prompt, "width": self.width, "height": self.height, "num_steps": self.num_steps}
        if negative_prompt: payload["negative_prompt"] = negative_prompt
        if seed: payload["seed"] = seed
        
        try:
            image_data = self._make_api_request(payload)
            return self._save_image_data(image_data, filename)
        except Exception as e:
            logger.error(f"Failed to generate {filename}: {e}. Using fallback.")
            return self._create_fallback_image(filename)

    def _generate_single_threaded(self, job: dict) -> dict:
        try:
            # Try generation with internal logic (which includes one API call)
            # If we want explicit retries here we can wrapper it, but for bulk we'll use generate_multiple's loop
            # Actually, let's let generate_image handle the single attempt.
            # But wait, the requirement is "retry at least 3 times".
            # The previous code had retry logic in `generate_multiple`. I will preserve and enhance that.
            
            # To avoid the fallback triggering immediately inside generate_image, we should probably separate "try generate" from "fallback".
            pass 
        except Exception as e:
            pass

    def _try_generate_image(self, prompt: str, filename: str, negative_prompt: str, seed: int) -> bytes:
        payload = {"prompt": prompt, "width": self.width, "height": self.height, "num_steps": self.num_steps}
        if negative_prompt: payload["negative_prompt"] = negative_prompt
        if seed: payload["seed"] = seed
        return self._make_api_request(payload)

    def generate_multiple(self, prompts: List[str], filenames: List[str], negative_prompts: List[Optional[str]],
                          max_workers: int = 5, max_retries: int = 3) -> List[Path]:
        """
        Generates multiple images in parallel.
        Retries up to max_retries.
        Falls back to black image if all retries fail.
        """
        num_prompts = len(prompts)
        jobs = [{
            "index": i, "prompt": prompts[i], "filename": filenames[i],
            "negative_prompt": negative_prompts[i], "seed": random.randint(1, 2**32 - 1)
        } for i in range(num_prompts)]
        
        results = [None] * num_prompts
        failed_jobs = jobs[:]

        for attempt in range(max_retries + 1):
            if not failed_jobs:
                break
            
            if attempt > 0:
                logger.info(f"Retrying {len(failed_jobs)} images (Attempt {attempt}/{max_retries})")
                time.sleep(2)

            current_batch = failed_jobs
            failed_jobs = []

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_job = {}
                for job in current_batch:
                    future = executor.submit(self._try_generate_image, job["prompt"], job["filename"], job["negative_prompt"], job["seed"])
                    future_to_job[future] = job

                for future in as_completed(future_to_job):
                    job = future_to_job[future]
                    try:
                        image_data = future.result()
                        path = self._save_image_data(image_data, job["filename"])
                        results[job["index"]] = path
                    except Exception as e:
                        logger.warning(f"Job {job['index']} failed: {e}")
                        failed_jobs.append(job)

        # Handle final failures with fallback
        for job in failed_jobs:
            logger.error(f"Job {job['index']} failed after all retries. using fallback.")
            path = self._create_fallback_image(job["filename"])
            results[job["index"]] = path

        return results
