from fastapi import Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import User, UserRole
from .platform_models import PlatformOperator
from .security import get_current_user


def is_platform_admin(db: Session, user: User) -> bool:
    explicit = db.scalar(
        select(PlatformOperator.id).where(PlatformOperator.user_id == user.id)
    )
    if explicit:
        return True

    # Compatibility for a fresh installation: before any platform-operator row
    # exists, only the oldest active owner can bootstrap platform administration.
    # Once a second tenant is provisioned, the explicit row becomes authoritative.
    operator_count = db.scalar(select(func.count(PlatformOperator.id))) or 0
    if int(operator_count) > 0:
        return False
    first_owner_id = db.scalar(
        select(User.id)
        .where(User.role == UserRole.OWNER, User.active.is_(True))
        .order_by(User.created_at, User.id)
        .limit(1)
    )
    return first_owner_id == user.id


def ensure_platform_operator(db: Session, user: User) -> PlatformOperator:
    row = db.scalar(
        select(PlatformOperator).where(PlatformOperator.user_id == user.id)
    )
    if row is not None:
        return row
    if not is_platform_admin(db, user):
        raise HTTPException(status_code=403, detail="No es administrador de plataforma")
    row = PlatformOperator(user_id=user.id)
    db.add(row)
    db.flush()
    return row


def require_platform_admin(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    if not is_platform_admin(db, user):
        raise HTTPException(status_code=403, detail="No es administrador de plataforma")
    return user
