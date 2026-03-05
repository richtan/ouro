from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DB_HOST: str = "postgres"
    DB_PORT: int = 5432
    DB_NAME: str = "ouro"
    DB_USER: str = "ouro"
    DB_PASSWORD: str = "changeme"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # LLM
    LLM_MODEL: str = "openai:gpt-4o-mini"
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    # LLM pricing per 1M tokens
    LLM_PRICE_INPUT_PER_M: float = 0.15
    LLM_PRICE_OUTPUT_PER_M: float = 0.60

    # Slurm (SLURMREST_URL set automatically by ./deploy/deploy-agent.sh)
    SLURMREST_URL: str = "http://localhost:6820"
    SLURMREST_JWT: str = ""

    # Blockchain
    BASE_RPC_URL: str = "https://mainnet.base.org"
    CHAIN_CAIP2: str = "eip155:8453"
    CHAIN_ID: int = 8453
    WALLET_PRIVATE_KEY: str = ""
    WALLET_ADDRESS: str = ""

    # Contracts
    PROOF_CONTRACT_ADDRESS: str = ""
    USDC_CONTRACT_ADDRESS: str = "0x..."

    # ERC-8021
    BUILDER_CODE: str = ""
    CODE_REGISTRY_ADDRESS: str = ""

    # ERC-8004
    ERC8004_AGENT_ID: str = ""
    ERC8004_REPUTATION_REGISTRY: str = ""

    # x402
    X402_FACILITATOR_URL: str = "https://x402.org/facilitator"
    CDP_API_KEY_ID: str = ""
    CDP_API_KEY_SECRET: str = ""

    # Container images
    ALLOWED_IMAGES: str = "base,python312,node20,pytorch,r-base"

    @property
    def allowed_images_set(self) -> set[str]:
        return {s.strip() for s in self.ALLOWED_IMAGES.split(",") if s.strip()}

    # Pricing
    PRICE_MARGIN_MULTIPLIER: float = 1.5
    MIN_PROFIT_PCT: float = 0.20
    INFRA_COST_PER_CPU_MINUTE: float = 0.0002

    # Auto-scaling (disabled by default)
    AUTO_SCALING_ENABLED: bool = False
    GCP_PROJECT: str = ""
    GCP_ZONE: str = "us-central1-a"
    GCP_CREDENTIALS_JSON: str = ""  # Service account key JSON (set in Doppler)
    SCALING_MAX_SPOT_NODES: int = 18
    SCALING_COOLDOWN_SECONDS: int = 30
    SCALING_IDLE_DRAIN_MINUTES: int = 5

    # CORS
    CORS_ORIGINS: str = "https://ourocompute.com,http://localhost:3000,http://localhost:3001"

    # Admin
    ADMIN_API_KEY: str = ""

    # Public URLs
    PUBLIC_DASHBOARD_URL: str = ""
    PUBLIC_API_URL: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
