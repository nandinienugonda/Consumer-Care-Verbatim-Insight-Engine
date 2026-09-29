"""Print a local development bearer token. Requires AUTH_DEV_MODE=true.

Example:
    python scripts/dev_token.py --tenant 00000000-0000-0000-0000-000000000001 \
        --user analyst-1 --role care_analyst --region south
"""

import argparse
from uuid import UUID

from ccvie.config import settings
from ccvie.core.models import Role
from ccvie.security.dev_tokens import mint_dev_token


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tenant", type=UUID, required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--role", type=Role, action="append", required=True)
    parser.add_argument("--region", action="append")
    parser.add_argument("--brand", action="append")
    parser.add_argument("--scope", action="append", default=[])
    args = parser.parse_args()
    print(
        mint_dev_token(
            settings,
            user_id=args.user,
            tenant_id=args.tenant,
            roles=args.role,
            regions=args.region,
            brands=args.brand,
            scopes=args.scope,
        )
    )


if __name__ == "__main__":
    main()
