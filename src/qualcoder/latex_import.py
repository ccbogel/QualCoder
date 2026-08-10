from __future__ import annotations

import re
from pathlib import Path

from pylatexenc.latex2text import LatexNodes2Text
from pylatexenc.macrospec import MacroSpec, MacroStandardArgsParser

from .text_decoding import decode_text_with_best_encoding


class LatexImportError(Exception):
    """Raised when LaTeX content cannot be imported."""


_INPUT_INCLUDE_RE = re.compile(r"\\(?:input|include)\s*(?:\[[^\]]*\]\s*)?\{[^{}]*\}")
_SECTIONING_MACROS = {"section", "subsection", "subsubsection", "paragraph", "subparagraph"}
_TIKZ_BEGIN_OPTIONS_RE = re.compile(r"^\s*\[(?:[^\[\]]|\[[^\[\]]*\])*\]\s*")
_TIKZ_NODE_OPTIONS_RE = re.compile(r"\[anchor=[^\]]*\]")
_TIKZ_NODE_PLACEMENT_RE = re.compile(r"\bat\s*\(current page\.[^)]+\)")
_TIKZ_TRAILING_SEMICOLON_RE = re.compile(r";\s*(?=\n|$)")
_RULE_DIMENSION_ARTIFACT_RE = re.compile(r"\b\d+\.\d+\d+\.\d+(?:pt|cm|mm|in|em|ex|bp|pc|dd|cc|sp)\b")
_LAYOUT_MACROS = {"rule", "includegraphics", "vspace", "vspace*", "hspace", "hspace*"}


def _build_latex_context():
    context = LatexNodes2Text().latex_context
    context.add_context_category(
        "qualcoder_layout_cleanup",
        macros=[
            MacroSpec("includegraphics", args_parser=MacroStandardArgsParser("[{")),
            MacroSpec("rule", args_parser=MacroStandardArgsParser("{{")),
            MacroSpec("vspace", args_parser=MacroStandardArgsParser("{")),
            MacroSpec("vspace*", args_parser=MacroStandardArgsParser("{")),
            MacroSpec("hspace", args_parser=MacroStandardArgsParser("{")),
            MacroSpec("hspace*", args_parser=MacroStandardArgsParser("{")),
        ],
        prepend=True,
    )
    return context


class _LatexToText(LatexNodes2Text):
    """Keep the conversion conservative and readable for coding purposes."""

    def __init__(self):
        super().__init__(latex_context=_build_latex_context())

    def macro_node_to_text(self, node):
        if node.macroname in _LAYOUT_MACROS:
            return ""
        if node.macroname in _SECTIONING_MACROS:
            title = ""
            if getattr(node, "nodeargd", None) is not None:
                for arg in reversed(node.nodeargd.argnlist):
                    if arg is not None and getattr(arg, "nodelist", None) is not None:
                        title = self.nodelist_to_text(arg.nodelist).strip()
                        if title:
                            break
            if title:
                return "\n\n" + title + "\n\n"
            return "\n\n"
        return super().macro_node_to_text(node)

    def environment_node_to_text(self, node):
        if node.environmentname == "tikzpicture":
            text = self.nodelist_to_text(node.nodelist)
            text = _TIKZ_BEGIN_OPTIONS_RE.sub("", text, count=1)
            text = _TIKZ_NODE_OPTIONS_RE.sub("", text)
            text = _TIKZ_NODE_PLACEMENT_RE.sub("", text)
            text = _TIKZ_TRAILING_SEMICOLON_RE.sub("", text)
            return text
        return super().environment_node_to_text(node)


def _normalize_plain_text(text: str) -> str:
    text = _RULE_DIMENSION_ARTIFACT_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def latex_to_plain_text(raw_tex: str) -> str:
    """Convert LaTeX source code into readable plain text."""

    if raw_tex == "":
        return ""
    cleaned_tex = _INPUT_INCLUDE_RE.sub(" ", raw_tex)
    try:
        text = _LatexToText().latex_to_text(cleaned_tex)
    except Exception as err:
        raise LatexImportError("Cannot convert LaTeX content to plain text.") from err
    return _normalize_plain_text(text or "")


def tex_file_to_plain_text(import_file: str | Path) -> str:
    """Read a LaTeX source file and convert it to readable plain text."""

    path = Path(import_file)
    try:
        raw_tex, _encoding = decode_text_with_best_encoding(path)
    except Exception as err:
        raise LatexImportError(f"Cannot import LaTeX file: {path.name}") from err
    if raw_tex.strip() == "":
        return ""
    try:
        return latex_to_plain_text(raw_tex)
    except Exception as err:
        raise LatexImportError(f"Cannot import LaTeX file: {path.name}") from err