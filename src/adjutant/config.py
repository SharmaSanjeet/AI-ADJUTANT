from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Adjutant"
    app_env: str = "local"
    database_url: str = "postgresql://adjutant:adjutant@localhost:5432/adjutant"
    seed_demo: bool = True
    model_provider: str = "mock"
    genesis_hash: str = "0" * 64
    mock_signing_key: str = "mock-signing-key-do-not-use-in-production"

    # Phase 5 limited automation. config_profile names the deployment shape;
    # the out-of-band profile moves human approvals to an independent channel.
    config_profile: Literal[
        "local/mock", "single-tenant", "out-of-band"
    ] = "local/mock"
    oob_topology: Literal[
        "same-tenant-degraded", "independent-control-plane"
    ] = "independent-control-plane"
    mock_oob_signing_key: str = "mock-oob-signing-key-do-not-use-in-production"
    kill_switch: bool = False
    rate_limit_per_hour: int = 5
    breaker_threshold: int = 3
    enable_autonomy_promotion: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def approval_channel(self) -> Literal["in-band", "out-of-band"]:
        return "out-of-band" if self.config_profile == "out-of-band" else "in-band"


@lru_cache
def get_settings() -> Settings:
    return Settings()
