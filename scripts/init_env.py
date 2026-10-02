import secrets
from pathlib import Path

path = Path(".env")
if not path.exists():
    template = Path(".env.example").read_text()
    # Two independent random local credentials; never commit .env.
    for _ in range(2):
        template = template.replace("REPLACE_WITH_GENERATED_LOCAL_SECRET", secrets.token_hex(32), 1)
    path.write_text(template)
    print("Generated .env; credentials are not displayed.")
else:
    print("Existing .env preserved.")
