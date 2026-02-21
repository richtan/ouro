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

    # Slurm
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
    USDC_CONTRACT_ADDRESS: str = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

    # ERC-8021
    BUILDER_CODE: str = ""
    CODE_REGISTRY_ADDRESS: str = ""

    # ERC-8004
    ERC8004_AGENT_ID: str = ""

    # x402
    X402_FACILITATOR_URL: str = "https://x402.org/facilitator"
    CDP_API_KEY_ID: str = ""
    CDP_API_KEY_SECRET: str = ""

    # Pricing
    PRICE_MARGIN_MULTIPLIER: float = 1.5
    MIN_PROFIT_PCT: float = 0.20
    INFRA_COST_PER_NODE_MINUTE: float = 0.0006

    # Public URLs
    PUBLIC_DASHBOARD_URL: str = ""
    PUBLIC_API_URL: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
