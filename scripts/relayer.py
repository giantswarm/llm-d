#!/usr/bin/env python3
"""Repack a container image's flattened filesystem into small zstd layers.

The input is the flattened filesystem of an image as ``crane export`` writes
it: one tar stream with every file exactly once, whiteouts already applied.
The output is an OCI image layout whose layers each hold at most
``--max-layer-bytes`` of that stream (uncompressed) and are zstd-compressed,
with the image config carried over unchanged except for ``rootfs.diff_ids``
and ``history``.

Two passes over the stream, so nothing but the compressed output is stored:

    crane export - - < image.tar | relayer.py plan  --max-layer-bytes N -o plan.json
    crane export - - < image.tar | relayer.py split --plan plan.json ... --out layout/

``plan`` sizes every directory of the stream and cuts the tree into items --
whole subtrees where they fit, otherwise a directory's own entry with its
direct files, and its subdirectories on their own -- then bin-packs the items
first-fit-decreasing. A directory whose direct files alone exceed the cap is
cut file by file. Hardlinks are always placed in their target's layer (a
hardlink is only valid within one layer), so nothing is ever copied and the
repacked filesystem is byte-for-byte the input.

``split`` streams every entry into its layer, emitting the entry's ancestor
directories (with the mode, owner, mtime and extended attributes the plan
recorded for them) into every layer that holds something beneath them, so
each layer applies cleanly on its own. The root directory entry is not
carried: runtimes create the root themselves.

Only the standard library is used; ``zstd`` is called as a subprocess.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time

BLOCK = 512
ZSTD_LAYER = "application/vnd.oci.image.layer.v1.tar+zstd"
OCI_CONFIG = "application/vnd.oci.image.config.v1+json"
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
OCI_INDEX = "application/vnd.oci.image.index.v1+json"


def normalize(name):
    """Tar entry name without the leading './' or '/', '' for the root."""
    while name.startswith("./"):
        name = name[2:]
    name = name.lstrip("/").rstrip("/")
    return "" if name == "." else name


def parent(name):
    i = name.rfind("/")
    return name[:i] if i >= 0 else ""


def ancestors(name):
    """Every proper ancestor of name, root ('') first."""
    out = [""]
    pos = name.find("/")
    while pos >= 0:
        out.append(name[:pos])
        pos = name.find("/", pos + 1)
    return out


def footprint(member):
    """Bytes the entry occupies in an uncompressed tar stream (approximate)."""
    size = BLOCK
    if member.isreg():
        size += (member.size + BLOCK - 1) // BLOCK * BLOCK
    if len(member.name) > 100 or len(member.linkname) > 100 or member.pax_headers:
        size += 2 * BLOCK  # a PAX extended header and its data block
    return size


def open_stream(fileobj, mode, **kwargs):
    return tarfile.open(fileobj=fileobj, mode=mode, copybufsize=1 << 20, **kwargs)


# ---------------------------------------------------------------- plan ----


class Tree:
    """Directory sizes of a tar stream: subtree totals and direct-file totals."""

    def __init__(self):
        self.subtree = {"": 0}
        self.direct = {"": 0}
        self.children = {"": set()}
        self.files = {"": []}  # (name, footprint) of non-directory direct children
        self.hardlinks = {}  # link name -> target name
        self.dir_meta = {}  # directory entry name -> metadata, for ancestor entries
        self.entries = 0

    def ensure_dir(self, name):
        if name in self.subtree:
            return
        self.subtree[name] = 0
        self.direct[name] = 0
        self.children[name] = set()
        self.files[name] = []
        p = parent(name)
        self.ensure_dir(p)
        self.children[p].add(name)

    def add(self, member):
        name = normalize(member.name)
        if not name:
            return
        self.entries += 1
        fp = footprint(member)
        if member.isdir():
            self.ensure_dir(name)
            self.direct[name] += fp
            for a in ancestors(name) + [name]:
                self.subtree[a] += fp
            self.dir_meta[name] = dir_metadata(member)
            return
        p = parent(name)
        self.ensure_dir(p)
        self.direct[p] += fp
        self.files[p].append((name, fp))
        for a in ancestors(name):
            self.subtree[a] += fp
        if member.islnk():
            self.hardlinks[name] = normalize(member.linkname)


DIR_FIELDS = ("mode", "uid", "gid", "mtime", "uname", "gname")


def dir_metadata(member):
    meta = {field: getattr(member, field) for field in DIR_FIELDS}
    if member.pax_headers:
        meta["pax_headers"] = dict(member.pax_headers)
    return meta


def dir_entry(name, meta):
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE
    for field in DIR_FIELDS:
        setattr(info, field, meta[field])
    info.pax_headers = dict(meta.get("pax_headers", {}))
    return info


def cut(tree, directory, cap):
    """Items covering `directory`: (kind, path-or-names, size)."""
    if tree.subtree[directory] <= cap:
        return [("subtree", directory, tree.subtree[directory])]
    items = []
    if tree.direct[directory] <= cap:
        items.append(("direct", directory, tree.direct[directory]))
    else:
        # The directory's own entry plus its direct files, cut file by file.
        own = tree.direct[directory] - sum(fp for _, fp in tree.files[directory])
        bins = pack([("file", n, fp) for n, fp in tree.files[directory]], cap - own)
        first = True
        for b in bins:
            names = [n for _, n, _ in b["items"]]
            size = b["size"] + (own if first else 0)
            items.append(("files", (directory, names, first), size))
            first = False
        if not bins:
            items.append(("files", (directory, [], True), own))
    for child in sorted(tree.children[directory]):
        items.extend(cut(tree, child, cap))
    return items


def pack(items, cap):
    """First-fit-decreasing bin packing; an oversize item gets its own bin."""
    bins = []
    for item in sorted(items, key=lambda it: it[2], reverse=True):
        size = item[2]
        for b in bins:
            if b["size"] + size <= cap:
                b["items"].append(item)
                b["size"] += size
                break
        else:
            bins.append({"items": [item], "size": size})
    return bins


def cmd_plan(args):
    tree = Tree()
    with open_stream(sys.stdin.buffer, "r|") as tin:
        for member in tin:
            tree.add(member)
    items = cut(tree, "", args.max_layer_bytes)
    bins = pack(items, args.max_layer_bytes)

    rules, overrides, groups = {}, {}, []
    for g, b in enumerate(bins):
        summary = []
        for kind, what, size in b["items"]:
            if kind == "subtree" or kind == "direct":
                rules[what] = {"kind": kind, "group": g}
                summary.append({"kind": kind, "path": "/" + what, "bytes": size})
            else:
                directory, names, with_dir = what
                for n in names:
                    overrides[n] = g
                if with_dir:
                    rules[directory] = {"kind": "self", "group": g}
                summary.append({"kind": "files", "path": "/" + directory, "count": len(names), "bytes": size})
        groups.append({"bytes": b["size"], "items": summary})

    # A hardlink lives in its target's layer; both resolve through the rules,
    # so only links whose rule differs from the target's need an override.
    moved = 0
    for link, target in tree.hardlinks.items():
        tg = lookup(target, rules, overrides)
        if lookup(link, rules, overrides) != tg:
            overrides[link] = tg
            moved += 1

    plan = {
        "max_layer_bytes": args.max_layer_bytes,
        "entries": tree.entries,
        "total_bytes": tree.subtree[""],
        "hardlinks": len(tree.hardlinks),
        "hardlinks_moved_to_target_layer": moved,
        "groups": groups,
        "rules": rules,
        "overrides": overrides,
        "directories": tree.dir_meta,
    }
    with open(args.output, "w") as f:
        json.dump(plan, f, indent=1, sort_keys=True)
    print(
        f"plan: {tree.entries} entries, {tree.subtree['']/1e9:.2f} GB, "
        f"{len(groups)} layers of <= {args.max_layer_bytes/1e9:.2f} GB, "
        f"{len(tree.hardlinks)} hardlinks ({moved} moved to their target's layer)",
        file=sys.stderr,
    )
    for g, grp in enumerate(groups):
        top = ", ".join(i["path"] for i in grp["items"][:4])
        more = f" +{len(grp['items'])-4}" if len(grp["items"]) > 4 else ""
        print(f"  layer {g:2d}: {grp['bytes']/1e9:6.3f} GB  {top}{more}", file=sys.stderr)


def lookup(name, rules, overrides):
    """The layer an entry belongs to under a plan."""
    g = overrides.get(name)
    if g is not None:
        return g
    rule = rules.get(name)
    if rule is not None:
        return rule["group"]
    for a in reversed(ancestors(name)):
        rule = rules.get(a)
        if rule is None:
            continue
        if rule["kind"] in ("subtree", "direct"):
            return rule["group"]
        # "self": the directory entry itself is here, its files carry overrides,
        # its subdirectories have rules of their own -- which the walk-up found
        # first. Only an implicit (entry-less) intermediate directory reaches this
        # line; it has no rule and no content of its own, so any layer is fine.
        return rule["group"]
    raise KeyError(f"no layer for {name!r}")


# ---------------------------------------------------------------- split ----


class HashingSink:
    """Forwards writes to a file object and keeps a sha256 and a byte count."""

    def __init__(self, target):
        self.target = target
        self.digest = hashlib.sha256()
        self.size = 0

    def write(self, data):
        self.digest.update(data)
        self.size += len(data)
        self.target.write(data)
        return len(data)

    def flush(self):
        self.target.flush()

    def close(self):
        self.target.close()


class Layer:
    def __init__(self, index, path, zstd_level, zstd_threads):
        self.index = index
        self.path = path
        self.file = open(path, "wb")
        self.proc = subprocess.Popen(
            ["zstd", "-q", f"-{zstd_level}", f"-T{zstd_threads}"],
            stdin=subprocess.PIPE,
            stdout=self.file,
        )
        self.sink = HashingSink(self.proc.stdin)
        self.tar = open_stream(self.sink, "w|", format=tarfile.PAX_FORMAT)
        self.dirs = set()
        self.entries = 0

    def close(self):
        self.tar.close()
        self.sink.close()
        rc = self.proc.wait()
        self.file.close()
        if rc != 0:
            raise RuntimeError(f"zstd exited {rc} for layer {self.index}")
        return {
            "diff_id": "sha256:" + self.sink.digest.hexdigest(),
            "uncompressed": self.sink.size,
            "compressed": os.path.getsize(self.path),
            "entries": self.entries,
        }


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def cmd_split(args):
    with open(args.plan) as f:
        plan = json.load(f)
    rules, overrides = plan["rules"], plan["overrides"]
    with open(args.config) as f:
        config = json.load(f)

    out = args.out
    blobs = os.path.join(out, "blobs", "sha256")
    work = os.path.join(out, "work")
    os.makedirs(blobs, exist_ok=True)
    os.makedirs(work, exist_ok=True)

    layers = [
        Layer(i, os.path.join(work, f"layer-{i:02d}.tar.zst"), args.zstd_level, args.zstd_threads)
        for i in range(len(plan["groups"]))
    ]
    directories = plan["directories"]
    started = time.monotonic()

    with open_stream(sys.stdin.buffer, "r|") as tin:
        for member in tin:
            name = normalize(member.name)
            if not name:
                continue
            member.name = name
            if member.islnk():
                member.linkname = normalize(member.linkname)
            layer = layers[lookup(name, rules, overrides)]
            for a in ancestors(name)[1:]:
                if a not in layer.dirs:
                    layer.dirs.add(a)
                    meta = directories.get(a)
                    if meta is not None:  # an implicit directory has no entry to carry
                        layer.tar.addfile(dir_entry(a, meta))
            if member.isdir():
                if name in layer.dirs:
                    continue  # emitted as an ancestor already, same metadata
                layer.dirs.add(name)
                layer.tar.addfile(member)
            elif member.isreg():
                layer.tar.addfile(member, tin.extractfile(member))
            else:
                layer.tar.addfile(member)
            layer.entries += 1

    results = [layer.close() for layer in layers]
    elapsed = time.monotonic() - started

    descriptors, diff_ids, history, report = [], [], [], []
    for layer, res, group in zip(layers, results, plan["groups"]):
        if res["entries"] == 0:
            os.unlink(layer.path)
            continue
        digest = sha256_file(layer.path)
        os.replace(layer.path, os.path.join(blobs, digest.split(":")[1]))
        descriptors.append({"mediaType": ZSTD_LAYER, "digest": digest, "size": res["compressed"]})
        diff_ids.append(res["diff_id"])
        paths = ", ".join(i["path"] for i in group["items"][:3])
        if len(group["items"]) > 3:
            paths += f" (+{len(group['items'])-3} more)"
        history.append(
            {
                "created": config.get("created"),
                "created_by": f"relayer.py: {res['entries']} entries, {paths}",
                "comment": f"repacked from {args.source_ref}@{args.source_digest}",
            }
        )
        report.append(
            {
                "layer": len(descriptors) - 1,
                "digest": digest,
                "diff_id": res["diff_id"],
                "compressed": res["compressed"],
                "uncompressed": res["uncompressed"],
                "entries": res["entries"],
                "items": group["items"],
            }
        )
    os.rmdir(work)

    config["rootfs"] = {"type": "layers", "diff_ids": diff_ids}
    config["history"] = history
    config_bytes = json.dumps(config, separators=(",", ":"), sort_keys=True).encode()
    config_digest = write_blob(blobs, config_bytes)

    manifest = {
        "schemaVersion": 2,
        "mediaType": OCI_MANIFEST,
        "config": {"mediaType": OCI_CONFIG, "digest": config_digest, "size": len(config_bytes)},
        "layers": descriptors,
        "annotations": {
            "org.opencontainers.image.base.name": args.source_ref,
            "org.opencontainers.image.base.digest": args.source_digest,
            "org.opencontainers.image.created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    }
    manifest_bytes = json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode()
    manifest_digest = write_blob(blobs, manifest_bytes)

    index = {
        "schemaVersion": 2,
        "mediaType": OCI_INDEX,
        "manifests": [
            {
                "mediaType": OCI_MANIFEST,
                "digest": manifest_digest,
                "size": len(manifest_bytes),
                "platform": {"architecture": config["architecture"], "os": config["os"]},
            }
        ],
    }
    with open(os.path.join(out, "index.json"), "w") as f:
        json.dump(index, f)
    with open(os.path.join(out, "oci-layout"), "w") as f:
        json.dump({"imageLayoutVersion": "1.0.0"}, f)

    total_c = sum(r["compressed"] for r in report)
    total_u = sum(r["uncompressed"] for r in report)
    summary = {
        "manifest_digest": manifest_digest,
        "config_digest": config_digest,
        "source_ref": args.source_ref,
        "source_digest": args.source_digest,
        "layers": report,
        "compressed_total": total_c,
        "uncompressed_total": total_u,
        "largest_compressed": max(r["compressed"] for r in report),
        "zstd_level": args.zstd_level,
        "seconds": round(elapsed, 1),
    }
    with open(args.report, "w") as f:
        json.dump(summary, f, indent=1)
    print(
        f"split: {len(report)} layers, {total_u/1e9:.2f} GB -> {total_c/1e9:.2f} GB zstd-{args.zstd_level} "
        f"in {elapsed:.0f}s; largest layer {summary['largest_compressed']/1e9:.3f} GB; manifest {manifest_digest}",
        file=sys.stderr,
    )


def write_blob(blobs, data):
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    with open(os.path.join(blobs, digest.split(":")[1]), "wb") as f:
        f.write(data)
    return digest


# ---------------------------------------------------------------- table ----


def gb(n):
    return f"{n/1e9:.2f} GB"


def short(path, limit=48):
    """A path as the table shows it: site-packages abbreviated, long tails elided."""
    path = path.replace("/opt/vllm/lib/python3.12/site-packages/", "site-packages/")
    if len(path) > limit:
        path = path[: limit - 1] + "…"
    return path


def cmd_table(args):
    """Markdown layer table of a split report, next to the source's layer shape."""
    with open(args.report) as f:
        report = json.load(f)
    with open(args.source_manifest) as f:
        source = json.load(f)
    src_sizes = sorted((layer["size"] for layer in source["layers"]), reverse=True)
    lines = [
        f"Source: {len(src_sizes)} layers, {gb(sum(src_sizes))} compressed, largest {gb(src_sizes[0])}"
        f" ({', '.join(gb(s) for s in src_sizes[:3])}, ...).",
        f"Repacked: {len(report['layers'])} layers, {gb(report['compressed_total'])} compressed"
        f" (zstd -{report['zstd_level']}) for {gb(report['uncompressed_total'])} of filesystem,"
        f" largest {gb(report['largest_compressed'])}.",
        "",
        "| Layer | Compressed | Uncompressed | Entries | Contents |",
        "|---|---|---|---|---|",
    ]
    for layer in report["layers"]:
        items = sorted(layer["items"], key=lambda i: i["bytes"], reverse=True)
        shown = ", ".join(
            f"`{short(i['path'])}`" + (f" ({i['count']} files)" if i["kind"] == "files" else "") for i in items[:3]
        )
        if len(items) > 3:
            shown += f" and {len(items) - 3} more"
        lines.append(
            f"| {layer['layer']} | {gb(layer['compressed'])} | {gb(layer['uncompressed'])} | {layer['entries']} | {shown} |"
        )
    print("\n".join(lines))


# ----------------------------------------------------------------- main ----


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plan", help="size the stream on stdin and write the layer plan")
    p.add_argument("--max-layer-bytes", type=int, default=1_200_000_000, help="uncompressed cap per layer")
    p.add_argument("-o", "--output", required=True, help="plan JSON to write")
    p.set_defaults(func=cmd_plan)

    s = sub.add_parser("split", help="repack the stream on stdin into an OCI layout under --out")
    s.add_argument("--plan", required=True)
    s.add_argument("--config", required=True, help="the source image's config JSON (crane config)")
    s.add_argument("--source-ref", required=True, help="the source image reference, recorded as base.name")
    s.add_argument("--source-digest", required=True, help="the source platform manifest digest, recorded as base.digest")
    s.add_argument("--out", required=True, help="OCI image layout directory to create")
    s.add_argument("--report", required=True, help="layer report JSON to write")
    s.add_argument("--zstd-level", type=int, default=9)
    s.add_argument("--zstd-threads", type=int, default=2)
    s.set_defaults(func=cmd_split)

    t = sub.add_parser("table", help="print a Markdown layer table from a split report")
    t.add_argument("--report", required=True)
    t.add_argument("--source-manifest", required=True, help="the source platform manifest JSON (crane manifest)")
    t.set_defaults(func=cmd_table)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
