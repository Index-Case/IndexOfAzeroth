# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import struct

SEQUENCE_SIZE = 64
BONE_SIZE = 88
VERTEX_SIZE = 48
TEXTURE_SIZE = 16
SECTION_SIZE = 48
BATCH_SIZE = 24
NO_GLOBAL = 0xFFFF


class Reader:
    def __init__(self, data, base=0):
        self.data, self.base = data, base

    def at(self, fmt, off):
        return struct.unpack_from("<" + fmt, self.data, self.base + off)

    def array(self, off):
        return self.at("II", off)

    def items(self, off, size, read):
        count, start = self.array(off)
        return [read(start + i * size) for i in range(count)]

    def values(self, off, fmt):
        count, start = self.array(off)
        return list(self.at(f"{count}{fmt}", start)) if count else []


def chunks(data):
    out, pos = {}, 0
    while pos + 8 <= len(data):
        name, size = struct.unpack_from("<4sI", data, pos)
        out[name.decode("ascii", "replace")] = data[pos + 8: pos + 8 + size]
        pos += 8 + size
    return out


def quat(v):
    return (v + 32768 if v < 0 else v - 32767) / 32767.0


def read_m2(data):
    parts = chunks(data)
    if "MD21" not in parts:
        raise ValueError("not a chunked model (no MD21)")
    md = Reader(parts["MD21"])
    magic, version = md.at("4sI", 0)
    if magic != b"MD20" or version < 264:
        raise ValueError(f"model format {magic!r} {version} isn't one this reads")
    (flags,) = md.at("I", 0x10)
    global_loops = md.values(0x14, "I")

    def sequence(o):
        sid, variation, duration, speed, sflags, freq, _, rmin, rmax, bin_, bout = md.at("HHIfIhHIIHH", o)
        return {"id": sid, "variation": variation, "duration": duration, "flags": sflags, "blendIn": bin_,
                "blendOut": bout, "next": md.at("h", o + 60)[0], "alias": md.at("H", o + 62)[0]}
    sequences = md.items(0x1C, SEQUENCE_SIZE, sequence)

    def track(o, fmt, convert=None):
        interp, glob = md.at("HH", o)
        times_n, times_at = md.array(o + 4)
        vals_n, vals_at = md.array(o + 12)
        size = struct.calcsize("<" + fmt) * (3 if interp in (2, 3) else 1)
        per = []
        for i in range(times_n):
            tn, ta = md.at("II", times_at + i * 8)
            vn, va = md.at("II", vals_at + i * 8)
            inside = ta + tn * 4 <= len(md.data) and va + vn * size <= len(md.data)
            if not inside or tn != vn:
                per.append(None)
                continue
            times = list(md.at(f"{tn}I", ta)) if tn else []
            vals = [md.at(fmt, va + k * size) for k in range(vn)]
            if convert:
                vals = [convert(v) for v in vals]
            per.append({"times": times, "values": [list(v) for v in vals]})
        return {"interp": interp, "global": None if glob == NO_GLOBAL else glob, "anims": per}

    def bone(o):
        key, bflags, parent, submesh = md.at("iIhH", o)
        return {"key": key, "flags": bflags, "parent": parent,
                "translation": track(o + 16, "3f"),
                "rotation": track(o + 36, "4h", lambda q: tuple(quat(c) for c in q)),
                "scale": track(o + 56, "3f"),
                "pivot": list(md.at("3f", o + 76))}
    bones = md.items(0x2C, BONE_SIZE, bone)

    def vertex(o):
        pos = md.at("3f", o)
        weights = md.at("4B", o + 12)
        indices = md.at("4B", o + 16)
        normal = md.at("3f", o + 20)
        uv = md.at("2f", o + 32)
        return pos, weights, indices, normal, uv
    vertices = md.items(0x3C, VERTEX_SIZE, vertex)

    def texture(o):
        ttype, tflags = md.at("II", o)
        return {"type": ttype, "flags": tflags}
    textures = md.items(0x50, TEXTURE_SIZE, texture)
    materials = [dict(zip(("flags", "blend"), md.at("HH", o))) for o in
                 (md.array(0x70)[1] + i * 4 for i in range(md.array(0x70)[0]))]
    weights = md.items(0x58, 20, lambda o: track(o, "h", lambda v: (v[0] / 32767.0,)))
    lo, hi = md.at("3f", 0xA0), md.at("3f", 0xAC)
    file_ids = {}
    for name in ("SFID", "TXID"):
        if name in parts:
            file_ids[name] = list(struct.unpack(f"<{len(parts[name]) // 4}I", parts[name]))
    return {"version": version, "flags": flags, "globalLoops": global_loops, "sequences": sequences, "bones": bones,
            "vertices": vertices, "textures": textures, "materials": materials, "textureWeights": weights,
            "textureCombos": md.values(0x80, "H"), "weightCombos": md.values(0x90, "H"),
            "bounds": [list(lo), list(hi)], "skins": file_ids.get("SFID", []), "textureFiles": file_ids.get("TXID", []),
            "hasSkeleton": "SKID" in parts, "animFiles": "AFID" in parts}


LIGHT_SIZE = 156
PARTICLE_SIZE = 492


def light_spot(data):
    parts = chunks(data)
    if "MD21" not in parts:
        return None
    md = Reader(parts["MD21"])
    if md.at("4s", 0)[0] != b"MD20" or len(md.data) < 0x130:
        return None

    def first(track, fmt):
        count, start = md.array(track + 12)
        for i in range(count):
            n, at = md.at("II", start + 8 * i)
            if n and at + struct.calcsize("<" + fmt) <= len(md.data):
                return list(md.at(fmt, at))
        return None
    lo, hi = md.at("3f", 0xA0), md.at("3f", 0xAC)

    def spot(at, colour=None, radius=None, own=False):
        reach = max(((x - at[0]) ** 2 + (y - at[1]) ** 2) ** 0.5 for x in (lo[0], hi[0]) for y in (lo[1], hi[1]))
        return {"at": at, "colour": colour, "reach": reach, "own": own, "radius": radius, "box": [list(lo), list(hi)]}
    lights = md.items(0x108, LIGHT_SIZE, lambda o: (list(md.at("3f", o + 4)), first(o + 56, "3f"), (first(o + 116, "f") or [None])[0]))
    if lights:
        return spot(*max(lights, key=lambda light: light[0][2]), own=True)
    flames = md.items(0x128, PARTICLE_SIZE, lambda o: list(md.at("3f", o + 8)))
    flames = [f for f in flames if all(v == v for v in f)]
    if flames:
        return spot(max(flames, key=lambda f: f[2]))
    return spot([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, hi[2]])


def read_skin(data):
    sk = Reader(data)
    if sk.at("4s", 0)[0] != b"SKIN":
        raise ValueError("not a skin file")
    lookup = sk.values(0x04, "H")
    indices = sk.values(0x0C, "H")

    def section(o):
        sid, level, vstart, vcount, istart, icount = sk.at("6H", o)
        return {"id": sid, "vertexStart": vstart + (level << 16), "vertexCount": vcount,
                "indexStart": istart + (level << 16), "indexCount": icount}

    def batch(o):
        bflags, priority, shader, section_i, geoset, color, material, layer, tex_count, tex_combo, coord_combo, \
            weight_combo, transform_combo = sk.at("BbHHHhHHHHHHH", o)
        return {"flags": bflags, "priority": priority, "shader": shader, "section": section_i, "color": color,
                "material": material, "layer": layer, "textureCount": tex_count, "textureCombo": tex_combo,
                "weightCombo": weight_combo}
    return {"lookup": lookup, "indices": indices, "sections": sk.items(0x1C, SECTION_SIZE, section),
            "batches": sk.items(0x24, BATCH_SIZE, batch)}
