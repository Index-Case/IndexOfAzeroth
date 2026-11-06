# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import re
import struct

import numpy as np

import game

MAGIC = b"WDC5"
HEAD = struct.Struct("<4sI128sIIIIIIIIIHHIIIIIII")
SECTION = struct.Struct("<QIIIIIIII")
FIELD = struct.Struct("<hH")
STORAGE = struct.Struct("<HHIIIII")
NONE, BITPACKED, COMMON, INDEXED, INDEXED_ARRAY, SIGNED = range(6)
HAS_OFFSET_MAP, HAS_RELATION_IDS, HAS_ID_LIST = 0x1, 0x2, 0x4


class Unreadable(ValueError):
    pass


class Encrypted(Unreadable):
    pass



class Column:

    def __init__(self, name, kind, bits, signed, array, notes):
        self.name, self.kind, self.bits, self.signed, self.array, self.notes = name, kind, bits, signed, array, notes

    @property
    def inline(self):
        return "noninline" not in self.notes


class Layout:
    def __init__(self, hashes, builds, ranges, columns):
        self.hashes, self.builds, self.ranges, self.columns = hashes, builds, ranges, columns


LINE = re.compile(r"^(?:\$([\w,]+)\$)?([\w]+)(?:<(u?)(\d+)>)?(?:\[(\d+)\])?$")
TYPE = re.compile(r"^(int|float|string|locstring)(?:<[^>]*>)?\s+([\w]+)\??$")


class Dbd:
    def __init__(self, columns, layouts):
        self.columns, self.layouts = columns, layouts

    def layout(self, layout_hash=None, build=None):
        want = f"{layout_hash:08X}" if isinstance(layout_hash, int) else (layout_hash or "").upper()
        by_hash = [x for x in self.layouts if want and want in x.hashes]
        by_build = [x for x in self.layouts if build and (build in x.builds or any(
            game.version_key(a) <= game.version_key(build) <= game.version_key(b) for a, b in x.ranges
            if a.split(".")[:3] == build.split(".")[:3]))]
        both = [x for x in by_hash if x in by_build]
        found = (both or by_hash or ([] if want else by_build))
        if not found:
            raise Unreadable(f"no definition of layout {want or '?'} for {build or '?'}")
        return found[0]


def parse_dbd(text):
    lines = [ln.split("//")[0].rstrip() for ln in text.replace("\r", "").split("\n")]
    if not lines or lines[0].strip() != "COLUMNS":
        raise Unreadable("a definition without COLUMNS")
    kinds, i = {}, 1
    while i < len(lines) and lines[i].strip():
        m = TYPE.match(lines[i].strip())
        if not m:
            raise Unreadable(f"a column line not as documented: {lines[i]!r}")
        kinds[m.group(2)] = m.group(1)
        i += 1
    layouts, block = [], []
    for line in lines[i:] + [""]:
        if line.strip():
            block.append(line.strip())
            continue
        if block:
            layouts.append(layout_block(block, kinds))
            block = []
    return Dbd(kinds, layouts)


def layout_block(block, kinds):
    hashes, builds, ranges, columns = set(), set(), [], []
    for line in block:
        if line.startswith("LAYOUT "):
            hashes.update(h.strip().upper() for h in line[7:].split(","))
        elif line.startswith("BUILD "):
            for part in line[6:].split(","):
                part = part.strip()
                if "-" in part:
                    a, b = part.split("-")
                    ranges.append((a, b))
                else:
                    builds.add(part)
        elif line.startswith("COMMENT"):
            continue
        else:
            m = LINE.match(line)
            if not m or m.group(2) not in kinds:
                raise Unreadable(f"a layout line not as documented: {line!r}")
            notes = set((m.group(1) or "").split(",")) - {""}
            kind = kinds[m.group(2)]
            bits = int(m.group(4)) if m.group(4) else None
            if kind == "int" and bits is None:
                raise Unreadable(f"an int column without its size: {line!r}")
            columns.append(Column(m.group(2), kind, bits, not m.group(3), int(m.group(5) or 0), notes))
    return Layout(hashes, builds, ranges, columns)



class Table:

    def __init__(self, layout_hash, table_hash, ids, fields, relation, copies):
        self.layout_hash, self.table_hash = layout_hash, table_hash
        self.ids, self.fields, self.relation, self.copies = ids, fields, relation, copies


def _bits(record, offset, size):
    start, end = offset >> 3, (offset + size + 7) >> 3
    return (int.from_bytes(record[start:end], "little") >> (offset & 7)) & ((1 << size) - 1)


def read_wdc5(data, zeros=(), columns=None):
    if len(data) < HEAD.size or data[:4] != MAGIC:
        raise Unreadable("not a WDC5 file")
    (_, version, _, record_count, field_count, record_size, string_size, table_hash, layout_hash, _, _, _, flags,
     id_index, total_fields, _, _, storage_size, common_size, pallet_size, section_count) = HEAD.unpack_from(data)
    if version != 5:
        raise Unreadable(f"WDC5 version {version}")
    at = HEAD.size
    if at + section_count * SECTION.size + total_fields * FIELD.size + storage_size > len(data):
        raise Unreadable("the file is cut short")
    sections = [SECTION.unpack_from(data, at + i * SECTION.size) for i in range(section_count)]
    at += section_count * SECTION.size
    structure = [FIELD.unpack_from(data, at + i * FIELD.size) for i in range(total_fields)]
    at += total_fields * FIELD.size
    empty = not record_count and not section_count and not storage_size
    if storage_size != field_count * STORAGE.size and not empty:
        raise Unreadable("field storage info not one per field")
    storage = [STORAGE.unpack_from(data, at + i * STORAGE.size) for i in range(storage_size // STORAGE.size)]
    at += storage_size
    pallet = data[at:at + pallet_size]
    at += pallet_size
    common_raw = data[at:at + common_size]
    at += common_size
    if at > len(data):
        raise Unreadable("the file is cut short")
    for start, end in zeros:
        if start < at:
            raise Encrypted("the header is encrypted")
    sparse = bool(flags & HAS_OFFSET_MAP)
    inline = [c for c in columns if c.inline] if columns is not None else None
    if inline is not None and len(inline) != field_count:
        raise Unreadable(f"the definition has {len(inline)} fields, the file {field_count}")
    if inline is not None:
        _check_sizes(storage, inline)

    pallet_at, common, p, c = [], [], 0, 0
    for f, (_, _, extra, kind, *_rest) in enumerate(storage):
        pallet_at.append(p)
        if kind in (INDEXED, INDEXED_ARRAY):
            p += extra
        if kind == COMMON:
            pairs = np.frombuffer(common_raw, "<u4", extra // 4, c).reshape(-1, 2)
            common.append(dict(zip(pairs[:, 0].tolist(), pairs[:, 1].tolist())))
            c += extra
        else:
            common.append(None)
    if p != pallet_size or c != common_size:
        raise Unreadable("pallet or common data not the fields' sizes")

    record_total = sum(s[2] * record_size for s in sections) if not sparse else 0
    left_out = [_left_out(s, data, zeros, sparse, record_size) for s in sections]
    strings, unread = _strings(sections, left_out, data, record_size) if not sparse else (b"", [])
    ids, fields, relation, copies = [], [[] for _ in range(field_count)], [], []
    records_before, skipped, opened = 0, [], []
    for section, out in zip(sections, left_out):
        key, offset, count, s_size, records_end, idl_size, rel_size, map_count, copy_count = section
        if out:
            skipped.append((key, count))
            records_before += count * record_size
            continue
        if key and count:
            opened.append((key, count))
        pos = offset
        if sparse:
            records_blob = data[offset:records_end]
            pos = records_end
        else:
            records_blob = data[pos:pos + count * record_size]
            pos += count * record_size + s_size
        id_list = np.frombuffer(data, "<u4", idl_size // 4, pos).tolist() if idl_size else []
        pos += idl_size
        copy = np.frombuffer(data, "<u4", copy_count * 2, pos).reshape(-1, 2).tolist() if copy_count else []
        pos += copy_count * 8
        offset_map = [struct.unpack_from("<IH", data, pos + i * 6) for i in range(map_count)] if sparse else []
        pos += map_count * 6 if sparse else 0
        rel = {}
        if rel_size:
            n, _, _ = struct.unpack_from("<III", data, pos)
            pairs = np.frombuffer(data, "<u4", n * 2, pos + 12).reshape(-1, 2).tolist()
            rel = {index: foreign for foreign, index in pairs}
            pos += rel_size
        map_ids = np.frombuffer(data, "<u4", map_count, pos).tolist() if sparse and map_count else []
        if pos + (len(map_ids) * 4) > len(data):
            raise Unreadable("a section past the file's end")

        rows = offset_map if sparse else range(count)
        for n, row in enumerate(rows):
            if sparse:
                start, size = row
                record = data[start:start + size]
                if not size:
                    continue
            else:
                record = records_blob[n * record_size:(n + 1) * record_size]
            values = _sparse_row(record, structure, inline) if sparse else None
            for f, (off_bits, size_bits, extra, kind, a, b, cnt) in enumerate(storage):
                if sparse:
                    fields[f].append(values[f])
                    continue
                col = inline[f] if inline is not None else None
                if kind == NONE:
                    width = 64 if col is not None and col.bits == 64 else 32
                    if col is not None and col.bits and col.bits < 32:
                        width = col.bits
                    count_here = max(1, size_bits // width)
                    base = off_bits
                    words = [_bits(record, base + i * width, width) for i in range(count_here)]
                    if col is not None and col.kind in ("string", "locstring"):
                        words = [_string(records_before + n * record_size + (base >> 3) + i * 4 - record_total, w,
                                         strings, unread) for i, w in enumerate(words)]
                    fields[f].append(words)
                elif kind in (BITPACKED, SIGNED):
                    v = _bits(record, off_bits, b)
                    if kind == SIGNED and v >> (b - 1):
                        v -= 1 << b
                    fields[f].append([v])
                elif kind == COMMON:
                    fields[f].append(None)
                elif kind == INDEXED:
                    i = _bits(record, off_bits, b)
                    fields[f].append([struct.unpack_from("<I", pallet, pallet_at[f] + i * 4)[0]])
                elif kind == INDEXED_ARRAY:
                    i = _bits(record, off_bits, b)
                    fields[f].append(list(struct.unpack_from(f"<{cnt}I", pallet, pallet_at[f] + i * 4 * cnt)))
                else:
                    raise Unreadable(f"field compression {kind}")
            if id_list:
                row_id = id_list[n]
            elif sparse and map_ids:
                row_id = map_ids[n]
            else:
                v = fields[id_index][-1][0]
                row_id = v
            ids.append(row_id)
            relation.append(rel.get(row_id if flags & HAS_RELATION_IDS else n))
        copies += copy
        records_before += count * record_size
    for f, kind_map in enumerate(common):
        if kind_map is None:
            continue
        default = storage[f][4]
        fields[f] = [[kind_map.get(i, default)] for i in ids]
    table = Table(layout_hash, table_hash, ids, fields, relation, copies)
    table.encrypted, table.opened = skipped, opened
    return table


def _check_sizes(storage, inline):
    for f, (_, size_bits, _, kind, _, _, cnt) in enumerate(storage):
        col = inline[f]
        n = col.array or 1
        if kind == NONE:
            want = (32 if col.kind != "int" else col.bits) * n
            if size_bits != want:
                raise Unreadable(f"{col.name} is {size_bits} bits in the file, the definition {want}")
        elif kind == INDEXED_ARRAY and cnt != n:
            raise Unreadable(f"{col.name} has {cnt} values in the file, the definition {n}")
        elif kind in (BITPACKED, SIGNED, COMMON, INDEXED) and col.array:
            raise Unreadable(f"{col.name} is an array in the definition, one value in the file")


def _left_out(section, data, zeros, sparse, record_size):
    key, offset, count, s_size, records_end, idl_size, rel_size, map_count, copy_count = section
    part_end = offset + (records_end - offset if sparse else count * record_size + s_size) + idl_size \
        + copy_count * 8 + (map_count * 6 if sparse else 0) + rel_size + (map_count * 4 if sparse else 0)
    return bool(count) and (any(start < part_end and end > offset for start, end in zeros)
                            or bool(key) and not any(data[offset:offset + min(64, record_size * count or 64)]))


def _strings(sections, left_out, data, record_size):
    blocks, unread, at = [], [], 0
    for (_, offset, count, s_size, *_rest), out in zip(sections, left_out):
        start = offset + count * record_size
        blocks.append(data[start:start + s_size])
        if out:
            unread.append((at, at + s_size))
        at += s_size
    return b"".join(blocks), unread


def _string(field_at, value, strings, unread):
    if value == 0:
        return ""
    at = field_at + value
    if not 0 <= at < len(strings):
        raise Unreadable("a string offset outside the file's string blocks")
    if any(start <= at < end for start, end in unread):
        raise Unreadable("a string in the block of a section the install holds encrypted")
    end = strings.index(b"\0", at)
    return strings[at:end].decode("utf-8")


def _sparse_row(record, structure, inline):
    if inline is None:
        raise Unreadable("a sparse table needs its definition")
    out, pos = [], 0
    for f, col in enumerate(inline):
        n = col.array or 1
        if col.kind in ("string", "locstring"):
            words = []
            for _ in range(n):
                end = record.index(b"\0", pos)
                words.append(record[pos:end].decode("utf-8"))
                pos = end + 1
        else:
            width = (32 - structure[f][0]) // 8
            words = [int.from_bytes(record[pos + i * width:pos + (i + 1) * width], "little") for i in range(n)]
            pos += n * width
        out.append(words)
    return out



UNDERSCORED = {"Index", "Order"}


def column_names(columns):
    out = []
    for col in columns:
        name = "_" + col.name if col.name in UNDERSCORED else col.name
        out += [f"{name}_{i}" for i in range(col.array)] if col.array else [name]
    return out


def _value(col, word):
    if col.kind in ("string", "locstring"):
        return word
    if col.kind == "float":
        return struct.unpack("<f", struct.pack("<I", word & 0xFFFFFFFF))[0]
    bits = col.bits or 32
    word &= (1 << bits) - 1
    if col.signed and word >> (bits - 1):
        word -= 1 << bits
    return word


def rows(table, layout):
    inline_index = {id(c): i for i, c in enumerate(c for c in layout.columns if c.inline)}
    out, by_id = [], {}
    for n, row_id in enumerate(table.ids):
        row = []
        for col in layout.columns:
            if not col.inline:
                if "id" in col.notes:
                    words = [row_id]
                elif "relation" in col.notes:
                    words = [table.relation[n] or 0]
                else:
                    raise Unreadable(f"a non-inline column {col.name} neither ID nor relation")
            else:
                words = table.fields[inline_index[id(col)]][n]
                if col.array and len(words) != col.array:
                    raise Unreadable(f"{col.name} has {len(words)} values, the definition {col.array}")
            row.append([_value(col, w) for w in words])
        out.append(row)
        by_id[row_id] = len(out) - 1
    id_col = next((i for i, c in enumerate(layout.columns) if "id" in c.notes), None)
    for new, old in table.copies:
        if old not in by_id:
            raise Unreadable(f"a copy of row {old}, which isn't there")
        row = [list(v) for v in out[by_id[old]]]
        if id_col is not None:
            row[id_col] = [new]
        out.append(row)
    return out


def hotfix_row(data, record_id, layout):
    row, pos = [], 0
    try:
        for col in layout.columns:
            if not col.inline and "id" in col.notes:
                row.append([record_id])
                continue
            words = []
            for _ in range(col.array or 1):
                if col.kind in ("string", "locstring"):
                    end = data.index(b"\0", pos)
                    words.append(data[pos:end].decode("utf-8"))
                    pos = end + 1
                    continue
                size = 4 if col.kind == "float" else (col.bits or 32) // 8
                if pos + size > len(data):
                    raise Unreadable("a hotfix row shorter than its columns")
                words.append(_value(col, int.from_bytes(data[pos:pos + size], "little")))
                pos += size
            row.append(words)
    except ValueError as e:
        raise Unreadable(f"a hotfix row not as its columns: {e}") from e
    if pos != len(data):
        raise Unreadable(f"a hotfix row of {len(data)} bytes, its columns {pos}")
    return row


def format_float(x):
    if x != x or x in (float("inf"), float("-inf")):
        return str(x).upper()
    scaled = x * 1e11
    if abs(scaled) < 2 ** 52:
        whole = math.floor(abs(scaled) + 0.5)
        x = math.copysign(whole, x) / 1e11
    if x == 0:
        return "0" if math.copysign(1, x) > 0 else "-0"
    text = f"{x:.14G}"
    if "E" in text:
        mantissa, exp = text.split("E")
        if "." in mantissa:
            mantissa = mantissa.rstrip("0").rstrip(".")
        if "." not in mantissa:
            mantissa += ".0"
        sign = "-" if exp.startswith("-") else "+"
        return f"{mantissa}E{sign}{int(exp.lstrip('+-'))}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


QUOTED = re.compile(r"[ ,\"\r\n]")


def cell(v):
    if isinstance(v, str):
        if v == "":
            return ""
        if not QUOTED.search(v):
            return v
        return '"' + v.replace('"', '""') + '"'
    if isinstance(v, float):
        return format_float(v)
    return str(v)


def to_csv(table, layout):
    return csv_of(rows(table, layout), layout)


def csv_of(table_rows, layout):
    lines = [",".join(column_names(layout.columns))]
    for row in table_rows:
        lines.append(",".join(cell(v) for values in row for v in values))
    return ("\n".join(lines) + "\n").encode("utf-8")
