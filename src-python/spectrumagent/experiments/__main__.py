"""Run explicit experiments: python -m spectrumagent.experiments --config ... --output-root ..."""
import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from backend.paths import AppPaths
from spectrumagent.data import DataError
from .schema import ExperimentConfig
from .service import ExperimentService


def main():
    parser = argparse.ArgumentParser(description="固定参数的光谱训练/独立测试数值实验")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        config = ExperimentConfig.model_validate_json(args.config.read_text("utf-8-sig"))
        paths = AppPaths(args.output_root.resolve())
        # Reject a misplaced output root before creating any files.
        specifications = (config.train, config.test)
        sources = []
        for spec in specifications:
            sources.extend(spec.paths if spec.kind == "npz" else
                           [m.header_path for m in spec.members] + [m.roi_path for m in spec.members])
        for value in sources:
            path = Path(value).resolve()
            if paths.root == path or paths.root.is_relative_to(path if path.is_dir() else path.parent):
                raise DataError("WRITE_TO_SOURCE_DENIED", "实验输出根不能位于输入数据目录中")
        paths.create_directories()
        service = ExperimentService(paths)
        result = service.run(config)
        print(json.dumps({"experiment_id": result["experiment_id"], "status": result["status"],
                          "result_dir": str(service.folder(result["experiment_id"])), "metrics": result["metrics"]},
                         ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (DataError, ValidationError, OSError) as error:
        payload = error.as_dict() if isinstance(error, DataError) else {"error": "INVALID_REQUEST", "detail": str(error)}
        print(json.dumps(payload, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
