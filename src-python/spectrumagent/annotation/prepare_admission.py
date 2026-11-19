"""Static admission evidence, not a scientific result or execution authorization.

2026-11-13 ruling: batch segmentation has no member-count or aggregate size
ceiling. This scanner only checks that an explicit scope is non-empty and its
members' metadata is readable. All former numeric ceilings (member count,
shape, bands, dtype, per-item and total source bytes, total pixels) are gone.
Content identity is snapshotted per member at batch start, and runtime memory
is enforced per item so a large scope degrades into isolated item failures
instead of a whole-batch veto.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from numbers import Integral

from spectrumagent.data import DataError


@dataclass
class Admission:
    assessment: str
    code: str
    constraint: str
    actual: int | str | None
    limit: int | str | None
    detail: str
    total_pixels: int = 0
    available: int = 0
    largest_reservation: int = 0

    def fields(self):
        return {'assessment': self.assessment, 'check_code': self.code,
                'constraint': self.constraint, 'actual': self.actual, 'limit': self.limit,
                'detail': self.detail, 'checked_at': datetime.now(timezone.utc).isoformat()}


def blocked(code, constraint, actual, limit, detail):
    return Admission('blocked', code, constraint, actual, limit, detail)


def scan(scope, registry, policy, *, resources=None, execution=False):
    """`scope` is a member list, or a frozen version dict kept for the legacy entry."""
    members = scope['members'] if isinstance(scope, dict) else scope
    if not members:
        return blocked('MEMBERS_UNAVAILABLE', 'members_available', 0, 0,
                       '本次范围为空，未开始处理。')
    total_pixels = largest = available = 0
    missing = unknown = False
    for member in members:
        try:
            dataset, _ = registry.get(member['cube_id'])
        except DataError:
            missing = True
            continue
        available += 1
        try:
            lines, samples, bands = dataset.shape
            if not all(isinstance(n, Integral) and not isinstance(n, bool) and n > 0
                       for n in (lines, samples, bands)):
                raise ValueError()
        except (TypeError, ValueError, AttributeError):
            # Unreadable metadata is a per-item fact, not a whole-batch veto:
            # execution verifies the real source and isolates the failed item.
            unknown = True
            continue
        total_pixels += lines * samples
        if resources is not None:
            largest = max(largest, resources.expected_bytes(dataset.shape))
        try:
            Path(dataset.header_path).stat().st_size + Path(dataset.data_path).stat().st_size
        except (OSError, TypeError, AttributeError):
            unknown = True
    if not available:
        return blocked('MEMBERS_UNAVAILABLE', 'members_available', 0, len(members),
                       '本次范围的成员当前均不可用，未开始处理。')
    result = Admission('unknown' if missing or unknown else 'within_profile',
                       'METADATA_UNAVAILABLE' if missing or unknown else 'WITHIN_PROFILE',
                       'metadata' if missing or unknown else 'static_profile', None, None,
                       '必要元数据或源文件状态尚不能完整核验；不能据此执行。' if missing or unknown else
                       '检查时未发现不可用成员；未检查运行时内存，源身份、冲突与缓存仍须在执行时逐项核验。')
    result.total_pixels, result.available, result.largest_reservation = total_pixels, available, largest
    return result


def check_version(versions, registry, version):
    from . import prepare_batch as policy
    frozen = versions.get_frozen(version)
    return frozen, scan(frozen['members'], registry, policy).fields()
