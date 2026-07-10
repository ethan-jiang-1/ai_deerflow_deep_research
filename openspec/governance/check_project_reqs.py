#!/usr/bin/env python3
# check_project_reqs.py — 项目级 Requirement ID registry 一致性检查（只读，不修改）
# Usage: python3 check_project_reqs.py [projectRoot]
#
# 借鉴自 deep-research 的 check-project-reqs.mjs，逻辑等价、技术栈换成本仓库的 Python
# 标准库（不引入 pyyaml——registry 的 ID 行用正则直接扫描，零外部依赖，永远可跑）。
#
# Requirement ID 只有一个硬约束: 全局唯一, 只增不删, 永不复用 (openspec/governance/req-registry.yaml)。
# 一个 id 有三种合法存在状态, 三态都不是则为 "孤儿" (疑似丢失/漏 sync):
#   alive   — 出现在 openspec/specs/ (OpenSpec main spec, 当前要构建的)
#   pending — 出现在 openspec/changes/<active>/specs/ (未归档 change 的 delta)
#   retired — 在 openspec/governance/req-registry.yaml 该行标记 [DEPRECATED] (合法废弃, id 占位永不复用)
#
# 四项检查:
#   1. duplicate      — 同一 id 被 ≥2 个不同的 main spec 文件 **声明** (归属冲突)
#   2. unregistered   — 出现在 specs/delta 但 registry 没有 (BUG-\d+ 是 bug ID, 不是 req ID, 不参与)
#   3. orphan         — registry 有, 但三态都不是 (静默丢失探测器)
#   4. reusedRetired  — 未归档 change **声明** 了已 [DEPRECATED] 的 id (禁止旧 id 指新语义)
#
# 声明 vs 引用: 只有 `> req: XXX-001, ...` 头部行算"声明"(归属)。正文 prose 里的
# 交叉引用 (如 "see CUT-002"、"per MEP-001") 只算"引用"——引用参与 unregistered/orphan
# 存在性判定, 但不参与 duplicate/reusedRetired 归属判定。

import re
import sys
from pathlib import Path

ID_RE = re.compile(r"^[A-Z]{3}-\d{3}$")
ID_SCAN_RE = re.compile(r"[A-Z]{3}-\d{3}")
BUG_ID_RE = re.compile(r"^BUG-\d+$")
REQ_HEADER_RE = re.compile(r"^\s*>\s*req:\s*(.+)$")
# registry 顶层 ID 行: `PREFIX-NNN: value`（缩进的 prefixes 子项不匹配）
REGISTRY_ID_LINE_RE = re.compile(r"^([A-Z]{3}-\d{3}):\s*(.*)$")


def strip_fenced_code_blocks(content: str) -> str:
    """把 ``` / ~~~ 围栏代码块内容替换成空行，避免代码示例里的 ID 被计入。逐行保持行号。"""
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = []
    active = None  # (marker_char, length)
    for line in lines:
        m = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
        if active is None:
            if m:
                active = (m.group(1)[0], len(m.group(1)))
                output.append("")
            else:
                output.append(line)
            continue
        output.append("")
        closing = re.match(r"^\s*(`{3,}|~{3,})\s*$", line)
        if closing and closing.group(1)[0] == active[0] and len(closing.group(1)) >= active[1]:
            active = None
    return "\n".join(output)


def parse_registry_ids(text: str):
    """返回 {id: value} —— 只取顶层 [A-Z]{3}-\\d{3} 行。不依赖 YAML 库。"""
    entries = {}
    for line in text.replace("\r\n", "\n").split("\n"):
        m = REGISTRY_ID_LINE_RE.match(line)
        if m:
            entries[m.group(1)] = m.group(2)
    return entries


def walk_into(dir_path: Path, sink: list):
    """递归 .md，收集 occurrence: {id, file, declared}。declared = 出现在 `> req:` 头部行。"""
    if not dir_path.exists():
        return
    for entry in sorted(dir_path.iterdir(), key=lambda p: p.name):
        if entry.is_dir():
            walk_into(entry, sink)
        elif entry.name.endswith(".md"):
            content = strip_fenced_code_blocks(entry.read_text(encoding="utf-8"))
            for line in content.split("\n"):
                declared = REQ_HEADER_RE.match(line) is not None
                for m in ID_SCAN_RE.finditer(line):
                    tok = m.group(0)
                    if BUG_ID_RE.match(tok):
                        continue  # bug ID, 不是 req ID
                    sink.append({"id": tok, "file": str(entry), "declared": declared})


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    registry_path = root / "openspec" / "governance" / "req-registry.yaml"
    specs_dir = root / "openspec" / "specs"
    changes_dir = root / "openspec" / "changes"

    if not registry_path.exists():
        print(f"Registry not found: {registry_path}", file=sys.stderr)
        return 1

    entries = parse_registry_ids(registry_path.read_text(encoding="utf-8"))
    retired = {k for k, v in entries.items() if "DEPRECATED" in str(v).upper()}
    registered = set(entries.keys())

    spec_occ: list = []
    delta_occ: list = []
    walk_into(specs_dir, spec_occ)
    if changes_dir.exists():
        for entry in sorted(changes_dir.iterdir(), key=lambda p: p.name):
            if not entry.is_dir() or entry.name == "archive":
                continue
            delta_specs = entry / "specs"
            if delta_specs.exists():
                walk_into(delta_specs, delta_occ)

    spec_id_set = {o["id"] for o in spec_occ}
    delta_id_set = {o["id"] for o in delta_occ}
    all_seen = spec_id_set | delta_id_set
    delta_declared_set = {o["id"] for o in delta_occ if o["declared"]}

    # 1. duplicate: 同一 id 被 ≥2 个不同 main spec 文件 **声明**（prose 交叉引用不算）
    spec_id_files: dict[str, set] = {}
    for o in spec_occ:
        if not o["declared"]:
            continue
        spec_id_files.setdefault(o["id"], set()).add(o["file"])
    duplicates = [i for i, files in spec_id_files.items() if len(files) > 1]

    # 2. unregistered: 声明与引用都参与（typo 探测）
    unregistered = sorted(i for i in all_seen if i not in registered)
    # 3. orphan（三态都不是）
    orphans = sorted(i for i in registered if i not in retired and i not in spec_id_set and i not in delta_id_set)
    # 4. reusedRetired: 未归档 change **声明** 了 [DEPRECATED] id
    reused_retired = sorted(i for i in delta_declared_set if i in retired)

    failed = False
    if duplicates:
        print("Duplicate IDs (same id in ≥2 spec files):", file=sys.stderr)
        for i in sorted(duplicates):
            files = ", ".join(sorted(f.replace(str(root) + "/", "") for f in spec_id_files[i]))
            print(f"  {i}: {files}", file=sys.stderr)
        failed = True
    if unregistered:
        print("Unregistered IDs (in specs/delta but not in registry):", ", ".join(unregistered), file=sys.stderr)
        failed = True
    if orphans:
        print("Orphan IDs (in registry but not alive / pending / retired):", file=sys.stderr)
        for i in orphans:
            print(f"  {i}: {str(entries[i]).strip()}", file=sys.stderr)
        print("  合法废弃 → 在 registry 该行加 [DEPRECATED]；疑似丢失 → 从 archive 找回或重建正文进 main spec。", file=sys.stderr)
        failed = True
    if reused_retired:
        print("Reused retired IDs (active change re-adds a [DEPRECATED] id):", ", ".join(reused_retired), file=sys.stderr)
        failed = True

    if failed:
        return 1

    total = len(spec_occ) + len(delta_occ)
    print(
        f"All project requirement IDs consistent: {len(registered)} registered "
        f"({len(retired)} retired, {len(orphans)} orphan), {total} occurrences in main specs/active deltas."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
