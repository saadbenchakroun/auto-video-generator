import json
import os
from pathlib import Path
from typing import Dict, Any, List

class ConfigManager:
    _instance = None
    _config = None
    # Resolve config path relative to project root (parent of app/)
    _config_path = str(Path(__file__).parent.parent / "config.json")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"Configuration file {self._config_path} not found.")
        
        with open(self._config_path, 'r') as f:
            self._config = json.load(f)

    def save_config(self):
        with open(self._config_path, 'w') as f:
            json.dump(self._config, f, indent=4)

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    # Type-safe accessors
    @property
    def api_keys(self) -> Dict[str, str]:
        return self._config.get("api_keys", {})

    @property
    def sheets_config(self) -> Dict[str, Any]:
        return self._config.get("google_sheets", {})

    @property
    def sheet_columns(self) -> Dict[str, str]:
        return self.sheets_config.get("columns", {"id": "id", "script": "script", "status": "created"})

    @property
    def sheet_settings(self) -> Dict[str, Any]:
        """Returns extra sheet settings like search_keyword and status_values."""
        return {
            "search_keyword": self.sheets_config.get("search_keyword", ""),
            "status_values": self.sheets_config.get("status_values", {
                "processing": "Processing",
                "done": "Done",
                "failed_audio": "Failed Audio",
                "failed_srt": "Failed SRT",
                "failed_images": "Failed Images",
                "failed_assembly": "Failed Assembly"
            })
        }

    @property
    def paths(self) -> Dict[str, str]:
        return self._config.get("paths", {})

    @property
    def video_settings(self) -> Dict[str, Any]:
        return self._config.get("video_settings", {})
    
    @property
    def ai_settings(self) -> Dict[str, Any]:
        return self._config.get("ai_settings", {})

    @property
    def caption_settings(self) -> Dict[str, Any]:
        return self._config.get("captions", {})

    def update_setting(self, section: str, key: str, value: Any):
        if section not in self._config:
            self._config[section] = {}
        self._config[section][key] = value
        self.save_config()

# Global instance
config = ConfigManager()
