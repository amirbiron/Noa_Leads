"""
יצירת משתמש חדש (owner / assistant) מ-CLI.

שימוש:
    python -m scripts.create_user --email noa@example.com --name "נועה" --role owner
"""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.constants import UserRole
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.user import User


async def create_user(email: str, name: str, role: str, password: str) -> None:
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            print(f"שגיאה: כבר קיים משתמש עם מייל {email}", file=sys.stderr)
            sys.exit(1)

        user = User(
            email=email,
            name=name,
            role=role,
            password_hash=hash_password(password),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"נוצר משתמש: {user.email} ({user.role})")


def main() -> None:
    parser = argparse.ArgumentParser(description="יצירת משתמש חדש")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--role",
        required=True,
        choices=[r.value for r in UserRole],
    )
    args = parser.parse_args()

    password = getpass.getpass("סיסמה: ")
    confirm = getpass.getpass("אישור סיסמה: ")
    if password != confirm:
        print("שגיאה: הסיסמאות לא תואמות", file=sys.stderr)
        sys.exit(1)
    if len(password) < 8:
        print("שגיאה: סיסמה חייבת להיות לפחות 8 תווים", file=sys.stderr)
        sys.exit(1)

    asyncio.run(create_user(args.email, args.name, args.role, password))


if __name__ == "__main__":
    main()
