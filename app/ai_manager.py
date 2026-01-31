
import json
import logging
import time
from typing import Optional, Dict
from cerebras.cloud.sdk import Cerebras
from app.config_manager import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AIManager:
    def __init__(self):
        self.api_key = config.api_keys.get("cerebras")
        self.model = config.ai_settings.get("model", "llama3.1-70b") # Cerebras supports specific models
        self.max_retries = config.ai_settings.get("max_retries", 3)
        
        if not self.api_key:
            logger.error("Cerebras API key not found in config.")
            raise ValueError("Cerebras API key is missing.")

        try:
            self.client = Cerebras(api_key=self.api_key)
            logger.info("Cerebras client initialized.")
        except Exception as e:
            raise ValueError(f"Failed to initialize Cerebras client: {e}")

    def generate_prompts(self, script_segment: str) -> str:
        """
        Generates an image prompt based on the provided script segment.
        Retries up to max_retries. Falls back to a random generic prompt on failure.
        """
        system_prompt = config.ai_settings.get("system_prompt", "Generate an SDXL prompt.")
        
        # We will use a simplified JSON schema for the output to ensure we get just the prompt
        schema = {
            "type": "object",
            "properties": {
                "detailed_prompt": {"type": "string", "description": "The SDXL optimized prompt"},
            },
            "required": ["detailed_prompt"]
        }

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Script segment: '{script_segment}'\n\nGenerate SDXL prompt:"}
        ]

        for attempt in range(1, self.max_retries + 1):
            try:
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    # Note: Cerebras SDK usage for JSON mode might differ slightly from OpenAI, 
                    # Check their documentation
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": "prompt_response", "strict": True, "schema": schema}
                    },
                    temperature=0.7,
                    max_tokens=500
                )
                
                content = completion.choices[0].message.content
                data = json.loads(content)
                prompt = data.get("detailed_prompt")
                
                if prompt:
                    return prompt
                    
            except Exception as e:
                logger.warning(f"Attempt {attempt}/{self.max_retries} failed: {e}")
                time.sleep(1) 

        logger.error("All attempts to generate prompt failed. Using fallback.")
        return self._get_fallback_prompt()

    def _get_fallback_prompt(self) -> str:
        import random
        subjects = config.ai_settings.get("fallback_prompts", [
            "abstract cinematic background", 
            "dark ambiance"
        ])
        general_style = config.ai_settings.get("general_fallback_prompt", "cinematic, 4k")
        return f"{random.choice(subjects)}, {general_style}"

if __name__ == "__main__":
    try:
        ai = AIManager()
        print(ai.generate_prompts("They didn't break you, they revealed you."))
    except Exception as e:
        print(f"Error: {e}")
