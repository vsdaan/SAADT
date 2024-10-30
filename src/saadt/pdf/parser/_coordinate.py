"""
Coordinate parser module. Separate module such that scipy and numpy aren't needed.
"""

# mypy: disable-error-code="assignment,attr-defined"

import bisect
import dataclasses
import io
import math
from typing import Any, NamedTuple

import gi
import numpy as np
from scipy import spatial

gi.require_version("Poppler", "0.18")
from gi.repository import Poppler  # noqa: E402


class _Coordinate(NamedTuple):
    x: float
    y: float

    def dx(self, other: "_Coordinate") -> float:
        return abs(self.x - other.x) / 2

    def dy(self, other: "_Coordinate") -> float:
        return abs(self.y - other.y) / 2


@dataclasses.dataclass
class _Rectangle:
    x1: float
    y1: float
    x2: float
    y2: float
    _center: _Coordinate | None = dataclasses.field(default=None, init=False)

    def __setattr__(self, name: str, value: Any) -> None:
        if name != "_center":
            self._center = None
        super().__setattr__(name, value)

    def __lt__(self, other: "_Rectangle") -> bool:
        if round(abs(self.y1 - other.y1)) < 10:
            return self.x1 < other.x1
        return self.y1 < other.y1

    @staticmethod
    def combine(b1: "_Rectangle", b2: "_Rectangle") -> "_Rectangle":
        return _Rectangle(min(b1.x1, b2.x1), min(b1.y1, b2.y1), max(b1.x2, b2.x2), max(b1.y2, b2.y2))

    @property
    def center(self) -> _Coordinate:
        if self._center is None:
            self._center = _Coordinate((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)
        return self._center

    def height(self) -> float:
        return self.y2 - self.y1

    def width(self) -> float:
        return self.x2 - self.x1

    def contains(self, other: "_Rectangle") -> bool:
        return self.x1 <= other.x1 and self.x2 >= other.x2 and self.y1 <= other.y1 and self.y2 >= other.y2

    def dx(self, other: "_Rectangle") -> float:
        return max(self.x1 - other.x2, other.x1 - self.x2)

    def dy(self, other: "_Rectangle") -> float:
        return max(self.y1 - other.y2, other.y1 - self.y2)

    def distance(self, other: "_Rectangle") -> tuple[float, float, float]:
        dx = max(0.0, self.dx(other))
        dy = max(0.0, self.dy(other))

        return dx, dy, math.sqrt(dx**2 + dy**2)


@dataclasses.dataclass(frozen=True)
class _Token:
    x1: float
    y1: float
    x2: float
    y2: float
    char: str
    font_size: float

    __slots__ = ("x1", "y1", "x2", "y2", "char", "font_size", "_center")

    def __post_init__(self) -> None:
        object.__setattr__(self, "_center", _Coordinate((self.x1 + self.x2) / 2, self.y1 + (self.y2 - self.y1) / 2))

    @classmethod
    def from_rectangle(cls, char: str, font_size: float, rect: Poppler.Rectangle) -> "_Token":
        return cls(rect.x1, rect.y1, rect.x2, rect.y2, char, font_size)

    @property
    def center(self) -> _Coordinate:
        return self._center  # type: ignore

    def __lt__(self, other: "_Token") -> bool:
        sc = self.center
        oc = other.center

        if abs(sc.y - oc.y) < max(self.font_size, other.font_size) * 0.7:
            return sc.x < oc.x
        return sc.y < oc.y

    def dx(self, other: "_Token") -> float:
        return abs(self.x1 + self.x2 - other.x1 - other.x2) / 2

    def dy(self, other: "_Token") -> float:
        return abs(self.y1 + self.y2 - other.y1 - other.y2) / 2


class _TokenBlock(_Rectangle):
    tokens: dict[int, None]

    def __init__(self, tokens: list[int], x1: float, y1: float, x2: float, y2: float) -> None:
        super().__init__(x1, y1, x2, y2)
        self.tokens = dict.fromkeys(tokens)

    @classmethod
    def from_token(cls, i: int, token: _Token) -> "_TokenBlock":
        return cls([i], token.x1, token.y1, token.x2, token.y2)

    def add(self, i: int, token: _Token) -> None:
        self.tokens[i] = None
        self.x1 = min(self.x1, token.x1)
        self.x2 = max(self.x2, token.x2)
        self.y1 = min(self.y1, token.y1)
        self.y2 = max(self.y2, token.y2)

    def merge(self, other: "_TokenBlock") -> None:
        self.x1 = min(self.x1, other.x1)
        self.x2 = max(self.x2, other.x2)
        self.y1 = min(self.y1, other.y1)
        self.y2 = max(self.y2, other.y2)
        self.tokens.update(other.tokens)

    def overlaps(self, other: "_TokenBlock") -> bool:
        dx = self.dx(other)
        dy = self.dy(other)

        margin = 1
        if dx > 0 or dy > 0:
            return False

        return abs(dx) > margin or abs(dy) > margin


class CoordinatePageParser:
    escape_sub_superscript: bool

    blocks: list[_TokenBlock]
    tree: spatial.KDTree
    tokens: list[_Token]

    def __init__(self, page: Poppler.Page, escape_sub_superscript: bool = True):
        self.page = page
        self.escape_sub_superscript = escape_sub_superscript
        text = page.get_text()
        _, layout = page.get_text_layout()

        if len(text) < len(layout):
            # Poppler fails on some papers without explanation -> text == ""
            # or sometimes len(text) != len(layout), but if text is longer, we can still use it.
            raise RuntimeError("Text does not match layout. Poppler messed up!")

        attrs = page.get_text_attributes()
        self.tokens = []
        self.blocks = []

        attr_index = 0
        for index, rect in enumerate(layout):
            if not text[index].strip():
                # we use our own heuristic for space and newlines
                continue

            if attrs[attr_index].end_index < index:
                attr_index += 1

            token = _Token.from_rectangle(text[index], attrs[attr_index].font_size, rect)
            self.tokens.append(token)

        self.tokens.sort()
        self.tree = spatial.KDTree([t.center for t in self.tokens])

    def enter_special_script(self, token: _Token, ldy: float, lfs: float) -> bool:
        return self.escape_sub_superscript and ldy != 0 and 2 < ldy < token.font_size * 0.7 < lfs * 0.7

    def exit_special_script(self, prev_token: _Token, token: _Token, ldy: float) -> bool:
        return self.escape_sub_superscript and token.dy(prev_token) > 2 > ldy and token.font_size > prev_token.font_size

    def write_line(self, buffer: io.StringIO, tokens: list[_Token]) -> None:
        if len(tokens) == 0:
            return

        result = ""
        in_specialchars = False
        prev_token = tokens[0]

        line_height = np.median([t.center.y for t in tokens])
        assert isinstance(line_height, float)
        line_fs = np.median([t.font_size for t in tokens])
        for token in tokens:
            ldy = abs(token.center.y - line_height)

            if in_specialchars and self.exit_special_script(prev_token, token, ldy):
                result += "]"
                in_specialchars = False

            if prev_token.x2 < token.x1 and token.x1 - prev_token.x2 > token.font_size * 0.1:
                result += " "

            if not in_specialchars and self.enter_special_script(token, ldy, line_fs):
                result += "["
                in_specialchars = True

            result += token.char
            prev_token = token

        if in_specialchars:
            result += "]"

        buffer.write(result)

    def find_block(self, index: int) -> _TokenBlock | None:
        for block in self.blocks:
            if index in block.tokens:
                return block

        return None

    def process_neighbor(self, start_token: _Token, block: _TokenBlock, neighbors: list[int]) -> None:
        token = start_token
        while len(neighbors) > 0:
            for ni in neighbors:
                t2 = self.tokens[ni]
                if (
                    token.dy(t2) < token.font_size * 0.7
                    and ni not in block.tokens  # For performance
                    and self.find_block(ni) is None
                ):
                    block.add(ni, t2)

            # neighbors includes tokens that could be located before token.center.x but after
            # token.x1. We need to do this to include weird tokens like '?' above an '='.
            # Find a token after token.center.x or break. Otherwise, we could loop infinitely.
            token_i = None
            for i in neighbors:
                if round(self.tokens[i].center.x, 4) <= round(token.center.x, 4):
                    continue
                token_i = i
                break
            if token_i is None:
                break

            token = self.tokens[token_i]
            _, nn = self.tree.query(token.center, 10, p=2, distance_upper_bound=token.font_size * 2)
            next_neighbors = [
                n
                for n in nn
                if n < len(self.tokens)
                and n != token_i
                and self.tokens[n].center.x > token.x1
                and self.tokens[n].dy(token) < token.font_size * 0.7
                and self.tokens[n].dy(start_token) < start_token.font_size
            ]

            neighbors = next_neighbors

    def check_overlap(self, indices: list[int], blocks: list[_TokenBlock]) -> bool:
        temp = _Rectangle(
            min(b.x1 for b in blocks), min(b.y1 for b in blocks), max(b.x2 for b in blocks), max(b.y2 for b in blocks)
        )
        return not any(k for k in range(len(self.blocks)) if k not in indices and self.blocks[k].distance(temp)[2] == 0)

    def find_above(self, rect: _Rectangle) -> int | None:
        result, min_dy = None, float("inf")
        for k in range(len(self.blocks)):
            if rect.contains(self.blocks[k]):
                continue
            if self.blocks[k].y2 > rect.y1:
                continue
            dx, dy, d = self.blocks[k].distance(rect)
            if dx == 0 and dy < min_dy:
                min_dy = dy
                result = k

        return result

    def find_below(self, rect: _Rectangle) -> int | None:
        result, min_dy = None, float("inf")
        for k in range(len(self.blocks)):
            if rect.contains(self.blocks[k]):
                continue
            if self.blocks[k].y1 < rect.y2:
                continue
            dx, dy, d = self.blocks[k].distance(rect)
            if dx == 0 and dy < min_dy:
                min_dy = dy
                result = k

        return result

    def run(self) -> str:
        self.blocks = []

        for current in range(len(self.tokens)):
            if self.find_block(current) is not None:
                continue
            token = self.tokens[current]
            _, nn = self.tree.query(token.center, 10, p=1, distance_upper_bound=token.font_size * 1.5)
            prev_neighbors = [
                n
                for n in nn
                if n < len(self.tokens)
                and n != current
                and (self.tokens[n].center.x <= token.center.x or self.tokens[n].center.y < token.center.y)
                and self.tokens[n].dy(token) < token.font_size
            ]
            next_neighbors = [
                n
                for n in nn
                if n < len(self.tokens)
                and n != current
                and self.tokens[n].center.x > token.center.x
                and self.tokens[n].dy(token) < token.font_size * 0.7
            ]

            block = None
            if len(prev_neighbors) > 0:
                for ni in prev_neighbors:
                    # prefer same line
                    block = self.find_block(ni)
                    if block is not None:
                        break

            if block is None:
                block = _TokenBlock.from_token(current, token)
                self.blocks.append(block)
            else:
                block.add(current, token)

            if len(next_neighbors) > 0:
                self.process_neighbor(token, block, next_neighbors)

        # First pass, merge overlapping blocks
        i = 0
        while i < len(self.blocks):
            b1 = self.blocks[i]
            j = i + 1
            while j < len(self.blocks):
                b2 = self.blocks[j]
                if b1.overlaps(b2):
                    b1.merge(b2)
                    del self.blocks[j]
                else:
                    j += 1
            i += 1

        # Third pass, merge small pieces that are on the same line
        # and couldn't be merged before due to overlap
        i = -1
        while i < len(self.blocks) - 1:
            i += 1
            b1 = self.blocks[i]

            b1_fs = self.tokens[next(iter(b1.tokens))].font_size
            if b1.height() > 2 * b1_fs:
                continue

            j = i
            while j < len(self.blocks) - 1:
                j += 1

                b2 = self.blocks[j]
                b2_fs = self.tokens[next(iter(b2.tokens))].font_size
                if b2.height() > 2 * b2_fs:
                    continue

                if math.floor(b1.center.dy(b2.center)) == 0 and self.check_overlap([i, j], [b1, b2]):
                    k1 = self.find_below(b1)
                    k2 = self.find_below(b2)
                    if k1 != k2:
                        continue

                    k = self.find_below(_Rectangle.combine(b1, b2))
                    if k is not None and self.blocks[k].dy(b1) < 2 * b1_fs:
                        bi = [i, j]
                        bs = [b1, b2]

                        l = j
                        is_overlap = False
                        while l < len(self.blocks) - 1:
                            is_overlap = self.check_overlap([*bi, k], [*bs, self.blocks[k]])

                            l += 1
                            b3 = self.blocks[l]
                            if abs(b2.height() - b3.height()) > b2_fs * 0.3:
                                continue
                            if math.floor(b2.center.dy(b3.center)) == 0 and self.check_overlap([*bi, l], [*bs, b3]):
                                if is_overlap and not self.check_overlap([*bi, l, k], [*bs, b3, self.blocks[k]]):
                                    break
                                bi.append(l)
                                bs.append(b3)
                        if is_overlap:
                            for ki in range(len(bs) - 1, 0, -1):
                                bs[ki - 1].merge(bs[ki])
                                del self.blocks[bi[ki]]
                            j -= 1

        # Second pass, paragraph merging
        i = 0
        while i < len(self.blocks):
            b1 = self.blocks[i]
            j = i + 1
            while j < len(self.blocks):
                b2 = self.blocks[j]
                dx, dy, d = b1.distance(b2)
                font_size = self.tokens[next(iter(b2.tokens))].font_size
                if round(dx) == 0 and dy < font_size and self.check_overlap([i, j], [b1, b2]):
                    b1.merge(b2)
                    del self.blocks[j]
                else:
                    j += 1
            i += 1

        # Merge column blocks forward
        i = 0
        while i < len(self.blocks):
            b1 = self.blocks[i]

            j = self.find_below(b1)
            if j is not None:
                b2 = self.blocks[j]
                font_size = self.tokens[next(iter(b2.tokens))].font_size
                dx, dy, d = b1.distance(b2)
                if (
                    b1.center.dx(b2.center) < font_size
                    and dy < font_size
                    or (abs(b1.x1 - b2.x1) < font_size or abs(b1.x2 - b2.x2) < font_size)
                    and dy < font_size * 2
                ):
                    if self.check_overlap([i, j], [b1, b2]):
                        b1.merge(b2)
                        del self.blocks[j]
                        i -= 1
            i += 1

        # Merge big same-width columns
        i = -1
        while i < len(self.blocks) - 1:
            i += 1
            b1 = self.blocks[i]
            b1_fs = self.tokens[next(iter(b1.tokens))].font_size
            if b1.height() < 2 * b1_fs:
                continue

            j = self.find_below(b1)
            if j is not None:
                b2 = self.blocks[j]
                font_size = self.tokens[next(iter(b2.tokens))].font_size
                if b2.height() < 2 * font_size:
                    continue
                if (
                    abs(b1.x1 - b2.x1) < font_size
                    and abs(b1.x2 - b2.x2) < font_size * 0.7
                    and self.check_overlap([i, j], [b1, b2])
                ):
                    b1.merge(b2)
                    del self.blocks[j]
                    i -= 1

        # try horizontal merging
        i = 0
        while i < len(self.blocks):
            b1 = self.blocks[i]
            j = i + 1
            merged = False
            while j < len(self.blocks):
                b2 = self.blocks[j]
                dx, dy, d = b1.distance(b2)
                font_size = self.tokens[next(iter(b2.tokens))].font_size

                if (
                    dx == 0
                    and ((b1.x1 - font_size * 0.7) < b2.x1 or b1.center.dx(b2.center) < font_size)
                    and (b1.x2 + font_size * 0.7) > b2.x2
                    and dy < font_size * 2
                ):
                    # find horizontal candidate
                    k = j + 1
                    while k < len(self.blocks):
                        b3 = self.blocks[k]
                        dx, dy, d = b2.distance(b3)
                        if dy == 0 and b1.distance(b3)[0] == 0 and self.check_overlap([j, k], [b2, b3]):
                            # column block
                            b2.merge(b3)
                            del self.blocks[k]
                        else:
                            k += 1

                    # try merging these new blocks
                    if self.check_overlap([i, j], [b1, b2]):
                        # column block
                        b1.merge(b2)
                        del self.blocks[j]
                        j -= 1
                        merged = True
                j += 1
            if not merged:
                i += 1

        blocks = self.sort_blocks()

        buffer = io.StringIO()
        for block in blocks:
            prev_token: _Token = self.tokens[next(iter(block.tokens))]

            line: list[_Token] = []
            heights: list[float] = [prev_token.center.y]
            for i in block.tokens:
                token = self.tokens[i]

                line_height = heights[math.floor(len(heights) / 2)]
                assert isinstance(line_height, float)
                dy = abs(token.center.y - line_height)

                if prev_token.dy(token) > token.font_size * 0.7 and prev_token.dx(token) > token.font_size:
                    self.write_line(buffer, line)
                    newlines = max(1, min(3, math.floor(dy / (token.font_size * 0.7))))
                    buffer.write("\n" * newlines)
                    line = []
                    heights = []

                line.append(token)
                bisect.insort(heights, token.center.y)
                prev_token = token

            if len(line) > 0:
                self.write_line(buffer, line)

            buffer.write("\n" * 3)

        return buffer.getvalue()

    def sort_blocks(self) -> list[_TokenBlock]:
        # One final sorting of the blocks
        y_min = min(self.blocks, key=lambda b: b.y1).y1
        y_max = max(self.blocks, key=lambda b: b.y2).y2
        header = []
        left = []
        right = []
        footer = []
        center = []

        page_center = self.page.get_size().width / 2

        for block in self.blocks:
            font_size = self.tokens[next(iter(block.tokens))].font_size
            if round(block.y1) == round(y_min) and (
                block.height() < 3 * font_size or block.x1 < page_center < block.x2
            ):
                header.append(block)
            elif round(block.y2) == round(y_max) and (
                block.height() < 3 * font_size or block.x1 < page_center < block.x2
            ):
                footer.append(block)
            elif block.x2 < page_center:
                left.append(block)
            elif block.x1 > page_center:
                right.append(block)
            else:
                center.append(block)

        min_left_y = self.page.get_size().height if len(left) == 0 else round(left[0].y1)
        max_left_y = 0 if len(left) == 0 else round(left[-1].y2)
        min_right_y = self.page.get_size().height if len(right) == 0 else round(right[0].y1)
        max_right_y = 0 if len(right) == 0 else round(right[-1].y2)

        new_footer = []
        for _ in range(len(center)):
            block = center.pop(0)
            if round(block.y2) <= min_left_y and round(block.y2) <= min_right_y:
                header.append(block)
            elif round(block.y1) >= max_left_y and round(block.y1) >= max_right_y:
                new_footer.append(block)
            else:
                center.append(block)

        new_footer.extend(footer)
        footer = new_footer

        if len(center) > 0:
            new_center = []
            for _ in range(len(center)):
                b1 = center.pop(0)
                j = 0
                while j < len(left):
                    b2 = left[j]
                    if b2.y2 <= b1.y1 + 1:
                        new_center.append(b2)
                        del left[j]
                    else:
                        j += 1

                j = 0
                while j < len(right):
                    b2 = right[j]
                    if b2.y2 <= b1.y1 + 1:
                        new_center.append(b2)
                        del right[j]
                    else:
                        j += 1

                j = 0
                while j < len(left):
                    b2 = left[j]
                    if b1.y1 < b2.center.y < b1.y2:
                        new_center.append(b2)
                        del left[j]
                    else:
                        j += 1

                new_center.append(b1)
                j = 0
                while j < len(right):
                    b2 = right[j]
                    if b1.y1 < b2.center.y < b1.y2:
                        new_center.append(b2)
                        del right[j]
                    else:
                        j += 1

            center = new_center

        result = []
        result.extend(header)
        result.extend(center)
        result.extend(left)
        result.extend(right)
        result.extend(footer)

        return result
