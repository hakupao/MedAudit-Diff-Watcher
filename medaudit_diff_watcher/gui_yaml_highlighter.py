from __future__ import annotations

import re

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextDocument


class YamlSyntaxHighlighter(QSyntaxHighlighter):
    _MAPPING_RE = re.compile(
        r"""^(\s*)(-\s+)?((?:"[^"\\]*(?:\\.[^"\\]*)*"|'[^']*(?:''[^']*)*'|[A-Za-z0-9_.-]+))(\s*:\s*)(.*)$"""
    )
    _LIST_VALUE_RE = re.compile(r"^(\s*-\s+)(.+)$")
    _LIST_MARKER_RE = re.compile(r"^\s*(-)\s*")
    _BOOL_NULL_RE = re.compile(r"\b(?:true|false|yes|no|on|off|null|~)\b", re.IGNORECASE)
    _NUMBER_RE = re.compile(r"(?<![\w.-])[-+]?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][-+]?\d+)?(?![\w.-])")
    _DQ_STRING_RE = re.compile(r'"([^"\\]|\\.)*"')
    _SQ_STRING_RE = re.compile(r"'([^']|'')*'")
    _ANCHOR_ALIAS_RE = re.compile(r"(?<!\w)[&*][A-Za-z0-9_.-]+")
    _TAG_RE = re.compile(r"(?<!\w)![A-Za-z0-9_./:-]+")
    _PATH_RE = re.compile(r"(?<![\w/])(?:[A-Za-z]:\\|\\\\)[^\s#]+")
    _URL_RE = re.compile(r"https?://[^\s#]+")

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)

        self._fmt_key = self._fmt("#0b3d91")
        self._fmt_separator = self._fmt("#b45309")
        self._fmt_plain_value = self._fmt("#0f5132")
        self._fmt_list_marker = self._fmt("#0b7285")
        self._fmt_bool_null = self._fmt("#b42318")
        self._fmt_number = self._fmt("#5b21b6")
        self._fmt_string = self._fmt("#9f1239")
        self._fmt_anchor_alias = self._fmt("#0c4a6e")
        self._fmt_tag = self._fmt("#c2410c")
        self._fmt_path = self._fmt("#166534")
        self._fmt_url = self._fmt("#1d4ed8", underline=True)
        self._fmt_comment = self._fmt("#6b7280", italic=True)

    def highlightBlock(self, text: str) -> None:
        comment_start = self._find_comment_start(text)
        code = text[:comment_start] if comment_start >= 0 else text

        mapping_match = self._MAPPING_RE.match(code)
        if mapping_match:
            marker_start, marker_end = mapping_match.span(2)
            if marker_end > marker_start >= 0:
                self.setFormat(marker_start, marker_end - marker_start, self._fmt_list_marker)
            key_start, key_end = mapping_match.span(3)
            sep_start, sep_end = mapping_match.span(4)
            value_start, value_end = mapping_match.span(5)
            self.setFormat(key_start, key_end - key_start, self._fmt_key)
            self.setFormat(sep_start, sep_end - sep_start, self._fmt_separator)
            if value_end > value_start:
                self.setFormat(value_start, value_end - value_start, self._fmt_plain_value)
                self._highlight_value_segment(code[value_start:value_end], value_start)
        else:
            list_match = self._LIST_MARKER_RE.match(code)
            if list_match:
                marker_start, marker_end = list_match.span(1)
                self.setFormat(marker_start, marker_end - marker_start, self._fmt_list_marker)

            list_value_match = self._LIST_VALUE_RE.match(code)
            if list_value_match:
                value_start, value_end = list_value_match.span(2)
                self.setFormat(value_start, value_end - value_start, self._fmt_plain_value)
                self._highlight_value_segment(code[value_start:value_end], value_start)

        if comment_start >= 0:
            self.setFormat(comment_start, len(text) - comment_start, self._fmt_comment)

    def _highlight_value_segment(self, value_text: str, offset: int) -> None:
        self._apply_pattern(value_text, self._URL_RE, self._fmt_url, offset)
        self._apply_pattern(value_text, self._PATH_RE, self._fmt_path, offset)
        self._apply_pattern(value_text, self._TAG_RE, self._fmt_tag, offset)
        self._apply_pattern(value_text, self._ANCHOR_ALIAS_RE, self._fmt_anchor_alias, offset)
        self._apply_pattern(value_text, self._BOOL_NULL_RE, self._fmt_bool_null, offset)
        self._apply_pattern(value_text, self._NUMBER_RE, self._fmt_number, offset)
        self._apply_pattern(value_text, self._DQ_STRING_RE, self._fmt_string, offset)
        self._apply_pattern(value_text, self._SQ_STRING_RE, self._fmt_string, offset)

    def _apply_pattern(self, text: str, pattern: re.Pattern[str], fmt: QTextCharFormat, offset: int = 0) -> None:
        for match in pattern.finditer(text):
            start, end = match.span()
            self.setFormat(offset + start, end - start, fmt)

    def _find_comment_start(self, text: str) -> int:
        in_single = False
        in_double = False
        i = 0
        while i < len(text):
            ch = text[i]
            if in_single:
                if ch == "'":
                    if i + 1 < len(text) and text[i + 1] == "'":
                        i += 2
                        continue
                    in_single = False
                i += 1
                continue

            if in_double:
                if ch == "\\":
                    i += 2
                    continue
                if ch == '"':
                    in_double = False
                i += 1
                continue

            if ch == "'":
                in_single = True
                i += 1
                continue
            if ch == '"':
                in_double = True
                i += 1
                continue

            if ch == "#" and (i == 0 or text[i - 1].isspace()):
                return i
            i += 1
        return -1

    def _fmt(
        self,
        color_hex: str,
        *,
        weight: QFont.Weight | None = None,
        italic: bool = False,
        underline: bool = False,
        background_hex: str | None = None,
    ) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color_hex))
        if background_hex is not None:
            fmt.setBackground(QColor(background_hex))
        if weight is not None:
            fmt.setFontWeight(int(weight))
        if italic:
            fmt.setFontItalic(True)
        if underline:
            fmt.setFontUnderline(True)
        return fmt
