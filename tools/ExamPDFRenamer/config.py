"""Configuration management for ExamPDFRenamer."""

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "tesseract_path": "",
    "poppler_path": "",
    "ocr_languages": "eng+chi_tra",
    "filename_template": "[{year}][{publisher}][{subject}]Mock Exam[{mock_number}][{paper}][{part}].pdf",
    "confidence_threshold": 0.9,
    "preserve_timestamps": True,
    "max_filename_length": 120,
    "ocr_dpi": 300,
    "debug_mode": False,
    "auto_install": True,
    "preprocessing": {
        "binarize": False,
        "deskew": False,
        "contrast": False,
    },
    "custom_publishers": [
        "Aristo", "Oxford", "Longman", "Pearson", "Pilot",
        "Marshall Cavendish", "Hong Kong Educational", "Pan Lloyds",
        "Manhattan", "Jing Kung", "Classroom", "Keys Press",
        "精工", "雅集", "牛津", "朗文", "培生", "啟思",
        "齡記", "樂思", "文達", "導師", "荃記",
    ],
    "subject_mapping_path": "",
    "db_path": "",
    "reports_dir": "",
}

APP_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = APP_DIR / "config.json"


def load_config() -> dict[str, Any]:
    """Load configuration, merging user overrides onto defaults."""
    config = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            # Shallow merge top-level, deep merge 'preprocessing'
            for k, v in user_cfg.items():
                if k == "preprocessing" and isinstance(v, dict):
                    config["preprocessing"].update(v)
                else:
                    config[k] = v
        except (json.JSONDecodeError, IOError):
            pass

    # Derived defaults
    if not config["db_path"]:
        config["db_path"] = str(APP_DIR / "processed_files.json")
    if not config["reports_dir"]:
        config["reports_dir"] = str(APP_DIR / "reports")
    if not config["subject_mapping_path"]:
        config["subject_mapping_path"] = str(APP_DIR / "subject_mapping.csv")
    return config


def save_config(config: dict[str, Any]) -> None:
    """Persist current configuration to config.json."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
