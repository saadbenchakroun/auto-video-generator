import os
import math
import logging
import traceback
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional
from pathlib import Path

# Custom Modules
from app.config_manager import config
from app.sheets_extractor import SheetsExtractor
from app.voice_generator import VoiceGenerator
from app.srt_generator import SRTGenerator, SRTConfig
from app.image_generator import ImageGenerator
from app.ai_manager import AIManager
from app.short_clips_maker import DynamicVideoGenerator
from app.video_assembler import VideoAssembler
from app.caption_burner import CaptionBurner, CaptionStyle
import mutagen.wave

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("pipeline.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Pipeline")

class VideoPipeline:
    def __init__(self):
        self.temp_dir = Path(config.paths.get("temp_dir", "temp_assets"))
        self.output_dir = Path(config.paths.get("output_dir", "final_output"))
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.sheets = SheetsExtractor(
            config.sheets_config["credentials_file"],
            config.sheets_config["sheet_id"],
            config.sheets_config["worksheet_name"]
        )
        self.ai_manager = AIManager()

    def run(self, max_videos: int = 5):
        logger.info(f"Starting Bulk Video Pipeline (Max Videos: {max_videos})...")
        
        # 1. Fetch Scripts
        pending_items = self._fetch_pending_scripts(max_videos)
        if not pending_items:
            logger.info("No pending scripts found.")
            return

        # 2. Bulk Audio Generation
        self._generate_audio_bulk(pending_items)

        # 3. Bulk SRT Generation
        self._generate_srt_bulk(pending_items)

        # 4. Prompt Generation
        self._generate_prompts_bulk(pending_items)

        # 5. Image Generation
        self._generate_images_bulk(pending_items)

        # 6. Video Assembly (Clips -> Stitch -> Audio -> Captions)
        self._assemble_videos_bulk(pending_items)

        # 7. Final Cleanup & Sheet Update
        self._update_sheets(pending_items)

        logger.info("Pipeline Execution Complete.")

    def _fetch_pending_scripts(self, limit: int) -> List[Dict[str, Any]]:
        logger.info(f"Fetching up to {limit} pending scripts from Google Sheets...")
        cols = config.sheet_columns
        settings = config.sheet_settings
        
        status_col = cols.get("status", "created")
        id_col = cols.get("id", "id")
        script_col = cols.get("script", "script")
        
        search_keyword = settings["search_keyword"]

        try:
            # Look for keyword or empty string
            rows = self.sheets.find_multiple_rows_and_get_data(status_col, search_keyword, max_results=limit)
            
            items = []
            for row_num, data in rows:
                script_id = data.get(id_col, str(row_num))
                safe_id = "".join(x for x in script_id if x.isalnum() or x in "-_")
                script_text = data.get(script_col, '')
                
                items.append({
                    "row_number": row_num,
                    "id": safe_id, 
                    "script_text": script_text,
                    "status": "Pending",
                    "files": {}
                })
            
            logger.info(f"Found {len(items)} scripts to process.")
            
            # Status update to processing
            processing_status = settings["status_values"].get("processing", "Processing")
            updates = []
            for item in items:
                updates.append((item["row_number"], status_col, processing_status))
            
            if updates:
                self.sheets.update_multiple_cells(updates)
                
            return items
        except Exception as e:
            logger.error(f"Failed to fetch scripts: {e}")
            traceback.print_exc()
            return []

    def _generate_audio_bulk(self, items: List[Dict]):
        logger.info("Phase 2: Bulk Audio Generation...")
        texts = {item["id"]: item["script_text"] for item in items if item["script_text"]}
        status_vals = config.sheet_settings["status_values"]
        
        if not texts:
            logger.warning("No texts to process for audio.")
            return

        try:
            vg = VoiceGenerator(
                model_path=config.paths["kokoro_model"],
                voice_path=config.paths["voice_path"]
            )
            
            results = vg.generate_batch(texts, str(self.temp_dir), prefix="voice")
            
            for item in items:
                res = results.get(item["id"])
                if res and res.success:
                    item["files"]["audio"] = res.output_path
                    try:
                        audio = mutagen.wave.WAVE(res.output_path)
                        item["audio_duration"] = audio.info.length
                    except:
                        item["audio_duration"] = res.duration
                else:
                    logger.error(f"Audio generation failed for {item['id']}: {res.error if res else 'Unknown'}")
                    item["status"] = status_vals.get("failed_audio", "Failed Audio")
                    
            vg.unload_model()
        except Exception as e:
            logger.error(f"Critical error in audio generation: {e}")
            traceback.print_exc()

    def _generate_srt_bulk(self, items: List[Dict]):
        logger.info("Phase 3: Bulk SRT Generation...")
        status_vals = config.sheet_settings["status_values"]
        
        audio_files = []
        srt_paths = []
        mapping = [] # to map back to items
        
        for item in items:
            if "audio" in item["files"] and item["status"] == "Pending":
                audio_path = item["files"]["audio"]
                srt_path = str(self.temp_dir / f"subs_{item['id']}.srt")
                audio_files.append(audio_path)
                srt_paths.append(srt_path)
                mapping.append(item)

        if not audio_files:
            return

        try:
            srt_gen = SRTGenerator(SRTConfig(model_path=config.paths["whisper_model"]))
            results = srt_gen.generate_multiple_srts(audio_files, srt_paths)
            srt_gen.unload_model()
            
            res_map = {path: success for path, success in results}
            
            for item in mapping:
                audio = item["files"]["audio"]
                if res_map.get(audio, False):
                    item["files"]["srt"] = str(self.temp_dir / f"subs_{item['id']}.srt")
                else:
                    logger.error(f"SRT generation failed for {item['id']}")
                    item["status"] = status_vals.get("failed_srt", "Failed SRT")
                    
        except Exception as e:
            logger.error(f"Critical error in SRT generation: {e}")
            traceback.print_exc()

    def _generate_prompts_bulk(self, items: List[Dict]):
        logger.info("Phase 4: Prompt Generation...")
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_item = {}
            for item in items:
                if item["status"] == "Pending":
                    duration = item.get("audio_duration", 0)
                    clip_dur = config.video_settings.get("clip_duration", 4.0)
                    num_images = math.ceil(duration / clip_dur)
                    item["num_images"] = max(1, num_images)
                    
                    chunk_size = len(item["script_text"]) // item["num_images"]
                    
                    for i in range(item["num_images"]):
                        start = i * chunk_size
                        end = start + chunk_size
                        segment = item["script_text"][start:end]
                        future = executor.submit(self.ai_manager.generate_prompts, segment)
                        future_to_item[future] = (item, i)

            for future in concurrent.futures.as_completed(future_to_item):
                item, index = future_to_item[future]
                if "prompts" not in item:
                    item["prompts"] = [None] * item["num_images"]
                
                try:
                    prompt = future.result()
                    item["prompts"][index] = prompt
                except Exception as e:
                    logger.error(f"Prompt gen failed for {item['id']} index {index}: {e}")
                    # Fallback comes from AIManager now, but just in case:
                    item["prompts"][index] = config.ai_settings.get("general_fallback_prompt", "abstract cinematic background")

    def _generate_images_bulk(self, items: List[Dict]):
        logger.info("Phase 5: Image Generation...")
        
        all_prompts = []
        all_filenames = []
        all_negatives = []
        
        job_map = [] 
        neg_prompt = config.video_settings.get("negative_prompt", "blurry, low quality")
        
        for item in items:
            if item["status"] == "Pending" and "prompts" in item:
                for i, prompt in enumerate(item["prompts"]):
                    if prompt:
                        filename = f"img_{item['id']}_{i}.png"
                        all_prompts.append(prompt)
                        all_filenames.append(filename)
                        all_negatives.append(neg_prompt)
                        job_map.append((item, i))
        
        if not all_prompts:
            return

        try:
            img_gen = ImageGenerator(
                account_id=config.api_keys["cloudflare_account_id"],
                api_token=config.api_keys["cloudflare_api_token"],
                output_dir=str(self.temp_dir),
                width=config.video_settings["width"],
                height=config.video_settings["height"]
            )
            
            paths = img_gen.generate_multiple(all_prompts, all_filenames, all_negatives)
            
            for idx, path in enumerate(paths):
                item, img_index = job_map[idx]
                if "image_paths" not in item:
                    item["image_paths"] = [None] * item.get("num_images", len(item["prompts"]))
                
                item["image_paths"][img_index] = path
                
        except Exception as e:
            logger.error(f"Global image generation failure: {e}")
            traceback.print_exc()

    def _assemble_videos_bulk(self, items: List[Dict]):
        logger.info("Phase 6: Assembly...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = []
            for item in items:
                if item["status"] == "Pending":
                     futures.append(executor.submit(self._process_single_video_assembly, item))
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Assembly uncaught error: {e}")

    def _process_single_video_assembly(self, item: Dict):
        status_vals = config.sheet_settings["status_values"]
        try:
            item_id = item["id"]
            if not item.get("image_paths") or not all(item["image_paths"]):
                logger.error(f"Missing images for {item_id}")
                item["status"] = status_vals.get("failed_images", "Failed Images")
                return

            video_width = config.video_settings["width"]
            video_height = config.video_settings["height"]
            fps = config.video_settings["fps"]
            clip_dur = config.video_settings["clip_duration"]

            # 1. Create Clips
            clip_maker = DynamicVideoGenerator()
            clip_paths = []
            
            for i, img_path in enumerate(item["image_paths"]):
                output_clip_name = str(self.temp_dir / f"clip_{item_id}_{i}.mp4")
                
                effects = []
                if i == 0:
                    effects = [
                        {'type': 'zoom', 'mode': 'in', 'start': 0, 'duration': clip_dur, 'easing': 'linear'},
                        {'type': 'fade', 'mode': 'out', 'start': clip_dur - 1.0, 'duration': 1.0}
                    ]
                elif i == len(item["image_paths"]) - 1:
                    effects = [
                        {'type': 'fade', 'mode': 'in', 'start': 0, 'duration': 1.0},
                        {'type': 'zoom', 'mode': 'out', 'start': 0, 'duration': clip_dur, 'easing': 'linear'},
                         {'type': 'fade', 'mode': 'out', 'start': clip_dur - 1.0, 'duration': 1.0}
                    ]
                else:
                    effects = [
                        {'type': 'fade', 'mode': 'in', 'start': 0, 'duration': 1.0},
                        {'type': 'fade', 'mode': 'out', 'start': clip_dur - 1.0, 'duration': 1.0}
                    ]

                clip_maker.create_video(
                    image_path=str(img_path),
                    output_path=output_clip_name,
                    effects_list=effects,
                    width=video_width,
                    height=video_height,
                    fps=fps,
                    duration=clip_dur
                )
                clip_paths.append(output_clip_name)

            # 2. Stitch
            assembler = VideoAssembler()
            stitched_path = str(self.temp_dir / f"stitched_{item_id}.mp4")
            assembler.stitch_videos(clip_paths, stitched_path)

            # 3. Add Audio
            video_audio_path = str(self.temp_dir / f"pre_caption_{item_id}.mp4")
            assembler.add_voice(
                video_path=stitched_path,
                audio_path=item["files"]["audio"],
                output_path=video_audio_path,
                duration_mode='audio'
            )

            # 4. Burn Captions
            final_path = str(self.output_dir / f"video_{item_id}.mp4")
            burner = CaptionBurner()
            
            c_conf = config.caption_settings
            style = CaptionStyle(
                font_path=config.paths["fonts"],
                font_size=c_conf.get("font_size", 52),
                font_color=tuple(c_conf.get("font_color", (255,255,255))),
                outline_color=tuple(c_conf.get("outline_color", (0,0,0))),
                outline_width=c_conf.get("outline_width", 3),
                position=c_conf.get("position", "bottom"),
                margin=c_conf.get("margin", 50)
            )

            burner.burn_captions(
                video_path=video_audio_path,
                srt_path=item["files"]["srt"],
                output_path=final_path,
                style=style
            )
            
            # Save Script Text
            script_file_path = str(self.output_dir / f"script_{item_id}.txt")
            with open(script_file_path, "w", encoding="utf-8") as f:
                f.write(item["script_text"])

            item["status"] = status_vals.get("done", "Done")
            item["final_path"] = final_path
            logger.info(f"Video completed: {final_path}")

        except Exception as e:
            logger.error(f"Assembly failed for {item.get('id')}: {e}")
            item["status"] = status_vals.get("failed_assembly", "Failed Assembly")
            traceback.print_exc()

    def _update_sheets(self, items: List[Dict]):
        logger.info("Phase 7: Updating Sheets...")
        status_col = config.sheet_columns.get("status", "created")
        done_val = config.sheet_settings["status_values"].get("done", "Done")
        
        updates = []
        for item in items:
            # Update if done or failed (anything other than Pending)
            if item["status"] != "Pending":
                updates.append((item["row_number"], status_col, item["status"]))
        
        if updates:
            self.sheets.update_multiple_cells(updates)

if __name__ == "__main__":
    pipeline = VideoPipeline()
    pipeline.run()