"""Only identifiers, counts and a digest cross the LLM boundary."""
from ..mat import MatStore


def export(sessions, arguments):
    row = MatStore(sessions.registry, sessions.paths).get(arguments.cube_id, arguments.version_id)
    return {"cube_id": row["cube_id"], "version_id": row["annotation_version_id"], "training_mat_id": row["id"],
            "n_spectra": row["n_spectra"], "n_bands": row["n_bands"], "n_classes": row["n_classes"],
            "sha256": row["sha256"], "status": "ready"}
