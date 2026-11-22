# backend/app/config.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH) if _ENV_PATH.exists() else ".env",
        extra="ignore"
    )

    database_url: str = "postgresql://intel_user:intel_dev_password@localhost:5432/email_intel"
    gemini_api_key: str = ""
    google_genai_api_version: str = "v1beta"
    decision_model_id: str = "gemini-3.1-flash-lite"
    flash_model_id: str = "gemini-3.1-flash-lite"
    embedding_model_id: str = "gemini-embedding-001"
    embedding_dim: int = 3072
    use_mock_ai: bool = False

    # Calibrated Gate Thresholds
    spam_quarantine_cutoff: float = 0.90
    spam_review_cutoff: float = 0.40
    pfa_ocr_cutoff: float = 0.60
    decision_promote_cutoff: float = 0.55
    ocr_vision_fallback_cutoff: float = 0.75
    matter_merge_cutoff: float = 0.78
    rerank_min_score: int = 2
    claim_entailment_cutoff: float = 0.70
    loop_pass_faithfulness: float = 0.80

    # Operational Guardrails
    min_image_bytes: int = 15_360
    min_image_px: int = 150
    max_langgraph_retries: int = 2
    stall_alert_days: int = 5

settings = Settings()
