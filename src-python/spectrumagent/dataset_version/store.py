"""Content identity and current dataset scope; historical SQL is migration-only."""
from hashlib import sha256
from spectrumagent.data import DataError


def cube_content_hash(header_hash, data_hash):
    return sha256((header_hash + '|' + data_hash).encode('ascii')).hexdigest()


def batch_content_hash(cube_hashes):
    return sha256('|'.join(sorted(cube_hashes)).encode('ascii')).hexdigest()


class DatasetScope:
    def __init__(self, registry):
        self.registry, self.database = registry, registry.database

    def get_frozen(self, _):
        # Old queued requests must fail rather than restore a historical scope.
        raise DataError('VERSION_FEATURE_REMOVED', '版本功能已移除，请直接选择当前样品')
