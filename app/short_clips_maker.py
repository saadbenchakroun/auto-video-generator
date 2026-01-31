import cv2
import numpy as np
import os

class Easing:
    """Handles mathematical curves for animation timing."""
    @staticmethod
    def linear(t): return t
    
    @staticmethod
    def ease_in_quad(t): return t * t
    
    @staticmethod
    def ease_out_quad(t): return t * (2 - t)
    
    @staticmethod
    def ease_in_cubic(t): return t * t * t
    
    @staticmethod
    def ease_out_cubic(t): return 1 - pow(1 - t, 3)

class DynamicVideoGenerator:
    def __init__(self):
        self.valid_easings = {
            'linear': Easing.linear,
            'ease_in': Easing.ease_in_quad,
            'ease_out': Easing.ease_out_quad,
            'cubic_in': Easing.ease_in_cubic,
            'cubic_out': Easing.ease_out_cubic
        }

    def _get_progress(self, current_frame, start_frame, duration_frames, easing_func_name):
        """Calculates the 0.0 to 1.0 progress of an effect based on current frame."""
        if current_frame < start_frame:
            return 0.0
        if current_frame > start_frame + duration_frames:
            return 1.0
        
        # Linear progress (0 to 1)
        t = (current_frame - start_frame) / duration_frames
        
        # Apply Easing Curve
        easing_func = self.valid_easings.get(easing_func_name, Easing.linear)
        return easing_func(t)

    def _apply_zoom(self, frame, progress, direction="in", max_zoom=1.5):
        """Applies Zoom In or Out."""
        h, w = frame.shape[:2]
        
        # Calculate scale factor
        if direction == "in":
            scale = 1.0 + (max_zoom - 1.0) * progress
        else: # out
            scale = max_zoom - (max_zoom - 1.0) * progress

        # Logic: We crop a center portion and resize it back up to fill the screen
        # New dimensions (smaller than original to simulate zoom)
        new_w, new_h = int(w / scale), int(h / scale)
        
        # Calculate center offsets
        x = (w - new_w) // 2
        y = (h - new_h) // 2
        
        cropped = frame[y:y+new_h, x:x+new_w]
        return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)

    def _apply_blur(self, frame, progress, mode="focus_in", max_k=51):
        """
        Applies Blur.
        focus_in: Starts blurry, goes clear.
        focus_out: Starts clear, goes blurry.
        """
        if mode == "focus_in":
            # Invert progress: 0.0 (start) should be max blur
            intensity = 1.0 - progress
        else:
            intensity = progress
            
        if intensity <= 0.01:
            return frame

        k_size = int(max_k * intensity)
        # Kernel size must be odd and positive
        if k_size % 2 == 0: k_size += 1
        if k_size < 1: k_size = 1
        
        return cv2.GaussianBlur(frame, (k_size, k_size), 0)

    def _apply_fade(self, frame, progress, mode="in"):
        """Applies Fade In (Black->Img) or Fade Out (Img->Black)."""
        h, w = frame.shape[:2]
        
        if mode == "in":
            alpha = progress
        else: # out
            alpha = 1.0 - progress
            
        # Create black background
        black = np.zeros((h, w, 3), dtype=np.uint8)
        
        # Blend: src1 * alpha + src2 * beta + gamma
        return cv2.addWeighted(frame, alpha, black, 1 - alpha, 0)

    def _apply_glitch(self, frame, progress, intensity=10):
        """
        Applies a 'Tech' glitch: RGB Split + Horizontal Slicing.
        Progress here determines the *probability* or *strength* of the glitch.
        """
        # If progress is low, maybe no glitch happens (optional), 
        # but here we assume progress controls intensity.
        
        h, w = frame.shape[:2]
        val = intensity * progress # How strong the glitch is right now
        
        if val < 0.1: return frame # Optimization: skip if effect is negligible

        result = frame.copy()

        # 1. RGB Split (Chromatic Aberration)
        offset = int(10 * val) # Pixel offset distance
        if offset > 0:
            b, g, r = cv2.split(result)
            # Shift Blue channel left, Red channel right
            b_shifted = np.roll(b, offset, axis=1)
            r_shifted = np.roll(r, -offset, axis=1)
            # Zero out the wrap-around parts to look cleaner
            b_shifted[:, :offset] = 0
            r_shifted[:, -offset:] = 0
            result = cv2.merge([b_shifted, g, r_shifted])

        # 2. Horizontal Slice/Shift (Scanline glitch)
        # We create random slices based on the intensity
        num_slices = int(5 * val) 
        for _ in range(num_slices):
            y_start = np.random.randint(0, h-10)
            h_slice = np.random.randint(2, 30) # Height of the slice
            shift = np.random.randint(-20, 20) * int(val)
            
            # Ensure bounds
            y_end = min(y_start + h_slice, h)
            
            # Apply roll to that specific row slice
            result[y_start:y_end, :] = np.roll(result[y_start:y_end, :], shift, axis=1)

        return result

    def create_video(self, 
                     image_path, 
                     output_path, 
                     effects_list, 
                     width=1920, 
                     height=1080, 
                     fps=30, 
                     duration=5):
        """
        Main pipeline to render the video.
        
        effects_list format:
        [
            {'type': 'zoom', 'mode': 'in', 'start': 0, 'duration': 5, 'easing': 'cubic_out'},
            {'type': 'glitch', 'intensity': 2, 'start': 2, 'duration': 1, 'easing': 'linear'}
        ]
        """
        
        # 1. Load and Prepare Image
        original = cv2.imread(image_path)
        if original is None:
            raise ValueError(f"Could not load image from {image_path}")
            
        # STRETCH image to target resolution (as requested)
        base_frame = cv2.resize(original, (width, height), interpolation=cv2.INTER_AREA)
        
        # 2. Setup Video Writer
        fourcc = cv2.VideoWriter_fourcc(*'mp4v') # mp4v is widely compatible
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        total_frames = int(duration * fps)
        
        print(f"Rendering {output_path}...")
        print(f"Resolution: {width}x{height} | FPS: {fps} | Total Frames: {total_frames}")

        # 3. Render Loop
        for i in range(total_frames):
            # Start with the fresh base frame every time
            current_frame = base_frame.copy()
            
            # Iterate through requested effects
            for effect in effects_list:
                e_start_time = effect.get('start', 0)
                e_dur_time = effect.get('duration', duration) # Default to full clip if not specified
                
                # Convert time (seconds) to frames
                start_f = int(e_start_time * fps)
                dur_f = int(e_dur_time * fps)
                
                # Calculate progress (0.0 to 1.0) with easing
                p = self._get_progress(i, start_f, dur_f, effect.get('easing', 'linear'))
                
                # If effect is finished or hasn't started (and p is 0 or 1), 
                # we still might need to apply it depending on logic, 
                # but usually we only modify if strictly active or holding final state.
                # Here we assume effects apply based on the calculated progress 'p'.
                
                eff_type = effect['type']
                
                if eff_type == 'zoom':
                    mode = effect.get('mode', 'in')
                    current_frame = self._apply_zoom(current_frame, p, direction=mode)
                
                elif eff_type == 'blur':
                    mode = effect.get('mode', 'focus_in')
                    current_frame = self._apply_blur(current_frame, p, mode=mode)
                    
                elif eff_type == 'fade':
                    mode = effect.get('mode', 'in')
                    current_frame = self._apply_fade(current_frame, p, mode=mode)
                    
                elif eff_type == 'glitch':
                    intensity = effect.get('intensity', 5)
                    # For glitch, we only apply if within the active time window
                    if start_f <= i <= start_f + dur_f:
                        current_frame = self._apply_glitch(current_frame, p, intensity=intensity)

            # Write frame
            out.write(current_frame)
            
            # Optional: Progress Log
            if i % 30 == 0:
                print(f"Processed frame {i}/{total_frames}")

        out.release()
        print("Done! Video saved.")

# ==========================================
# Example Usage / Driver Code
# ==========================================
if __name__ == "__main__":
    # Initialize Generator
    generator = DynamicVideoGenerator()
    
    # Create a dummy image for testing if you don't have one
    # (In production, you would provide a real path)
    if not os.path.exists("input.jpg"):
        dummy_img = np.zeros((600, 800, 3), dtype=np.uint8)
        # Draw some patterns so we can see the zoom/glitch
        cv2.rectangle(dummy_img, (100,100), (700,500), (255,0,0), -1)
        cv2.circle(dummy_img, (400,300), 100, (0,255,0), -1)
        cv2.putText(dummy_img, "TEST", (350, 300), cv2.FONT_HERSHEY_SIMPLEX, 2, (0,0,255), 5)
        cv2.imwrite("input.jpg", dummy_img)
    
    # CONFIGURATION FOR VIDEO 1
    # Goal: Zoom In + Start Blurry then Clear + Glitch in the middle
    effects_scenario_1 = [
        {
            'type': 'zoom', 
            'mode': 'in', 
            'start': 0, 
            'duration': 5, # Lasts full video
            'easing': 'cubic_out'
        },
        {
            'type': 'blur',
            'mode': 'focus_in', # Starts blurry, becomes sharp
            'start': 0,
            'duration': 2, # Clears up in first 2 seconds
            'easing': 'linear'
        },
        {
            'type': 'glitch',
            'intensity': 10,
            'start': 2.5, # Starts at 2.5 seconds
            'duration': 0.5, # Lasts 0.5 seconds
            'easing': 'linear' 
        }
    ]

    generator.create_video(
        image_path="Output/cabin.png",
        output_path="output_video.mp4",
        effects_list=effects_scenario_1,
        width=1920,
        height=1080,
        fps=30,
        duration=5
    )
    generator.create_video(
        image_path="Output/city.png",
        output_path="output_video2.mp4",
        effects_list=effects_scenario_1,
        width=1920,
        height=1080,
        fps=30,
        duration=5
    )

