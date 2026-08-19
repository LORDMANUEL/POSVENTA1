from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import utcnow, uuid4


class PlatformOperator(Base):
    """Global platform operator allowed to provision isolated tenants.

    The operator is still a normal tenant-scoped user for business data. This
    table grants only platform provisioning powers; it does not bypass tenant
    filters on POS, inventory, finance, media or any other business endpoint.
    """

    __tablename__ = "platform_operators"
    __table_args__ = (UniqueConstraint("user_id", name="uq_platform_operator_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
