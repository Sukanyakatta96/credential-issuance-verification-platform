"""Creates .env with freshly generated secrets. Refuses to overwrite an existing file."""
import secrets
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
target = root / ".env"
if target.exists():
    sys.exit(".env already exists; leaving it untouched.")
template = (root / ".env.example").read_text(encoding="utf-8")
lines = []
for line in template.splitlines():
    if line.startswith(("JWT_SECRET=", "SIGNING_MASTER_SECRET=")):
        lines.append(f"{line.split('=')[0]}={secrets.token_urlsafe(48)}")
    else:
        lines.append(line)
target.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Wrote {target} with newly generated secrets.")
