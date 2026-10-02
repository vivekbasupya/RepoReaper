from dataclasses import dataclass
from typing import Any

import tree_sitter_go as go
import tree_sitter_java as java
import tree_sitter_javascript as javascript
import tree_sitter_python as python
import tree_sitter_typescript as typescript
from tree_sitter import Language, Parser


@dataclass
class SyntaxAdapter:
    name: str
    extensions: tuple[str, ...]
    language: Language

    def symbols(self, source: bytes) -> list[dict[str, Any]]:
        tree = Parser(self.language).parse(source)
        symbols = []
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in {
                "function_definition",
                "function_declaration",
                "method_declaration",
                "class_definition",
                "class_declaration",
            }:
                name = node.child_by_field_name("name")
                symbols.append(
                    {
                        "name": name.text.decode() if name and name.text else "anonymous",
                        "kind": node.type,
                        "start_line": node.start_point.row + 1,
                        "end_line": node.end_point.row + 1,
                    }
                )
            stack.extend(reversed(node.children))
        return symbols


REGISTRY = (
    SyntaxAdapter("python", (".py",), Language(python.language())),
    SyntaxAdapter("javascript", (".js", ".jsx"), Language(javascript.language())),
    SyntaxAdapter("typescript", (".ts",), Language(typescript.language_typescript())),
    SyntaxAdapter("tsx", (".tsx",), Language(typescript.language_tsx())),
    SyntaxAdapter("go", (".go",), Language(go.language())),
    SyntaxAdapter("java", (".java",), Language(java.language())),
)


def detect(path: str) -> SyntaxAdapter | None:
    return next((a for a in REGISTRY if path.endswith(a.extensions)), None)
