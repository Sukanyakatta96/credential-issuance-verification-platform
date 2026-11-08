import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Config:
    database_path: str
    data_dir: str
    ground_truth_dir: str
    jwt_secret: str
    jwt_ttl_minutes: int
    signing_master_secret: str
    public_rate_limit_per_minute: int
    login_max_failures: int
    login_lockout_seconds: int

    @classmethod
    def from_env(cls, overrides: dict | None = None) -> "Config":
        load_env_file(PROJECT_ROOT / ".env")
        env = {**os.environ, **(overrides or {})}

        def required(name: str) -> str:
            value = env.get(name, "")
            if not value or value.startswith("CHANGE_ME"):
                raise RuntimeError(
                    f"{name} is not configured. Copy .env.example to .env and set a real value."
                )
            return value

        def resolve(name: str, default: str) -> str:
            path = Path(env.get(name, default))
            return str(path if path.is_absolute() else PROJECT_ROOT / path)

        return cls(
            database_path=resolve("DATABASE_PATH", "instance/credentials.db"),
            data_dir=resolve("DATA_DIR", "data/full"),
            ground_truth_dir=resolve("GROUND_TRUTH_DIR", "data/full"),
            jwt_secret=required("JWT_SECRET"),
            jwt_ttl_minutes=int(env.get("JWT_TTL_MINUTES", 480)),
            signing_master_secret=required("SIGNING_MASTER_SECRET"),
            public_rate_limit_per_minute=int(env.get("PUBLIC_RATE_LIMIT_PER_MINUTE", 60)),
            login_max_failures=int(env.get("LOGIN_MAX_FAILURES", 5)),
            login_lockout_seconds=int(env.get("LOGIN_LOCKOUT_SECONDS", 300)),
        )
