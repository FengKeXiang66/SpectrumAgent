"""User-declared exclusions scoped to the paths scanned for this operation."""
import json
from pathlib import Path
import re

from .schema import InputModel
from pydantic import Field


class ExclusionRules(InputModel):
    name_fragments: list[str] = Field(default_factory=list)
    prefixes: list[str] = Field(default_factory=list)
    codes: dict[str, str] = Field(default_factory=dict)

    def reason(self, path, root=None):
        path = Path(path)
        parts = path.relative_to(root).parts if root is not None else (path.name,)
        names = tuple(part.casefold() for part in parts)
        reasons = [f'关键词 {value}' for value in self.name_fragments
                   if value.strip() and any(value.casefold() in name for name in names)]
        reasons.extend(f'前缀 {value}' for value in self.prefixes
                       if value.strip() and any(name.startswith(value.casefold()) for name in names))
        reasons.extend(f'编码 {code}（{label}）' for code,label in self.codes.items()
                       if code.strip() and any(re.search(r'(?<![0-9])'+re.escape(code.casefold())+r'(?![0-9])', name)
                                               for name in names))
        return '、'.join(reasons)


def read_exclusions(path):
    document = json.loads(Path(path).read_text('utf-8-sig'))
    document.pop('说明', None)
    return ExclusionRules.model_validate(document)
