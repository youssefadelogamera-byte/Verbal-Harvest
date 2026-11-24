"""Settings, all from environment variables with local-first defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    db_path: Path
    packs_dir: Path
    default_pack: str
    # Any OpenAI-compatible endpoint. Default is LM Studio on this machine (open-weights models).
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    # Optional second model shown alongside the open-weights one. Never required.
    frontier_base_url: str | None
    frontier_api_key: str | None
    frontier_model: str | None
    web_host: str
    web_port: int
    mcp_port: int
    product_name: str = "Athar"
    demo_pack: str = "cambridge-school"  # what `athar demo` seeds the first time
    tls_cert: str | None = None      # a certificate file: the app then serves HTTPS
    tls_key: str | None = None
    language: str = "ar"             # the language the page opens in, and the agent words findings in
    arabic_wording: str = "fixed"    # "fixed": plain sentences written in code. "model": the model words them
    # The school this copy is for: shown in the top of the page, the installed app and the report.
    school_name: str = "Learning International Schools"
    school_name_ar: str = "مدارس التعليم العالمية"
    school_tagline: str = "AI-Powered · Future Skills · Wellbeing"
    branding_dir: Path = ROOT / "branding"  # put the school's logo here as logo.png, logo.svg, logo.jpg or logo.webp
    # True for the school's own records (`athar start`): no made-up data is ever created or offered.
    real_school: bool = False


def get_settings() -> Settings:
    env = os.environ.get
    return Settings(
        db_path=Path(env("ATHAR_DB", str(ROOT / "data" / "athar.db"))),
        packs_dir=Path(env("ATHAR_PACKS", str(ROOT / "packs"))),
        default_pack=env("ATHAR_PACK", "generic-maths"),
        llm_base_url=env("ATHAR_LLM_BASE_URL", "http://localhost:1234/v1"),
        llm_api_key=env("ATHAR_LLM_API_KEY", "lm-studio"),
        llm_model=env("ATHAR_LLM_MODEL", "qwen3.5-9b"),
        frontier_base_url=env("ATHAR_FRONTIER_BASE_URL"),
        frontier_api_key=env("ATHAR_FRONTIER_API_KEY"),
        frontier_model=env("ATHAR_FRONTIER_MODEL"),
        web_host=env("ATHAR_WEB_HOST", "127.0.0.1"),
        web_port=int(env("ATHAR_WEB_PORT", "8765")),
        mcp_port=int(env("ATHAR_MCP_PORT", "8766")),
        product_name=env("ATHAR_PRODUCT_NAME", "Athar"),
        demo_pack=env("ATHAR_DEMO_PACK", "cambridge-school"),
        tls_cert=env("ATHAR_TLS_CERT") or None,
        tls_key=env("ATHAR_TLS_KEY") or None,
        language=env("ATHAR_LANGUAGE", "ar") if env("ATHAR_LANGUAGE", "ar") in ("ar", "en") else "en",
        arabic_wording="model" if env("ATHAR_ARABIC_WORDING", "fixed") == "model" else "fixed",
        school_name=env("ATHAR_SCHOOL_NAME", "Learning International Schools"),
        school_name_ar=env("ATHAR_SCHOOL_NAME_AR", "مدارس التعليم العالمية"),
        school_tagline=env("ATHAR_SCHOOL_TAGLINE", "AI-Powered · Future Skills · Wellbeing"),
        branding_dir=Path(env("ATHAR_BRANDING", str(ROOT / "branding"))),
        real_school=env("ATHAR_REAL_SCHOOL", "") in ("1", "true", "yes"),
    )
