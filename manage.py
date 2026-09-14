"""CLI for managing API keys without going through the admin HTTP endpoints."""

import argparse

from app.db import create_api_key, get_api_key_by_key, get_session, init_db


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-key")
    create.add_argument("--name", required=True)
    create.add_argument("--credits", type=int, default=0)

    show = sub.add_parser("show-key")
    show.add_argument("key")

    args = parser.parse_args()
    init_db()

    with get_session() as session:
        if args.command == "create-key":
            api_key = create_api_key(session, args.name, args.credits)
            print(f"name={api_key.name} credits={api_key.credits}")
            print(f"key={api_key.key}")
        elif args.command == "show-key":
            api_key = get_api_key_by_key(session, args.key)
            if not api_key:
                print("not found")
                return
            print(f"name={api_key.name} credits={api_key.credits} active={api_key.active}")


if __name__ == "__main__":
    main()
