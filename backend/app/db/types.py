import datetime as dt

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Datetime column that stores naive UTC in the DB but is always
    returned to the app as a timezone-aware UTC datetime.

    MySQL/MariaDB DATETIME cannot store a timezone, so SQLAlchemy's
    timezone=True is silently ignored and fetched values come back naive.
    This type encodes them as aware UTC on read and strips the offset on
    write so comparisons and arithmetic stay consistent.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: dt.datetime | None, dialect) -> dt.datetime | None:
        if value is not None:
            if value.tzinfo is None:
                value = value.replace(tzinfo=dt.timezone.utc)
            value = value.astimezone(dt.timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value: dt.datetime | None, dialect) -> dt.datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value