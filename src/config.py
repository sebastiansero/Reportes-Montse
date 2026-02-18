import yaml
from pathlib import Path
from typing import Dict, Any

class ConfigLoader:
    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config_path = Path(config_path)
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Loads the YAML configuration file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found at {self.config_path}")
        
        with open(self.config_path, "r", encoding="utf-8") as file:
            return yaml.safe_load(file)

    @property
    def reports(self) -> Dict[str, Any]:
        return self._config.get("reports", {})

    @property
    def app_settings(self) -> Dict[str, Any]:
        return {k: v for k, v in self._config.items() if k != "reports"}

    def get_report_config(self, report_key: str) -> Dict[str, Any]:
        """Returns the configuration for a specific report."""
        return self.reports.get(report_key)
