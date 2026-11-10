"""Small-cell protection for the F9 plan aggregates (review of PR #167).

Shared by ``scripts/aggregate_sis_planes.py`` (which hides cells before writing) and ``stats_ficha_f9`` (which re-runs
the check on the published file and HOLDs on a leak). Standard library only, Python 3.11.

Model. Every published count is a sum over *atoms* (isapre × comercialización × has-cotizantes × modalidad). A cell
(group, set, split) is hidden when it has 1-4 plans (primary). A hidden count leaks when its atom vector lies in the
linear span of the published counts of the same metric, after removing atoms that published zeros reveal as empty:
that is exactly "it can be recovered by adding and subtracting published cells". Complementary cells are hidden
greedily until no hidden count is recoverable. Arithmetic is exact modulo a 61-bit prime.
"""
from __future__ import annotations

import heapq

MIN_PLANS = 5
PRIME = (1 << 61) - 1
SETS = {"todos": (None, None), "venta": ("S", None), "no_venta": ("N", None), "vigentes": (None, 1),
        "cerrados_con_cotizantes": ("N", 1)}
COMERS = ("S", "N", "?")
PRIMARY = f"<{MIN_PLANS} planes"
COMPLEMENTARY = "complementaria"


class Span:
    """Row space over GF(PRIME), sparse rows keyed by their lowest column (pivot)."""

    def __init__(self) -> None:
        self.rows: dict[int, dict[int, int]] = {}

    def reduce(self, v: dict[int, int]) -> dict[int, int]:
        v = {k: x % PRIME for k, x in v.items() if x % PRIME}
        heap = list(v)
        heapq.heapify(heap)
        seen = set()
        while heap:
            c = heapq.heappop(heap)
            if c in seen or c not in v:
                continue
            seen.add(c)
            row = self.rows.get(c)
            if row is None:
                continue
            f = v[c]
            for k, x in row.items():
                y = (v.get(k, 0) - f * x) % PRIME
                if y:
                    if k not in v:
                        heapq.heappush(heap, k)
                    v[k] = y
                else:
                    v.pop(k, None)
        return v

    def add(self, v: dict[int, int]) -> None:
        v = self.reduce(v)
        if v:
            p = min(v)
            inv = pow(v[p], PRIME - 2, PRIME)
            self.rows[p] = {k: x * inv % PRIME for k, x in v.items()}

    def contains(self, v: dict[int, int]) -> bool:
        return not self.reduce(v)


def cell_ids(grupos: dict) -> list[tuple[str, str, str]]:
    """(group, set, split) for every count cell; split '' is the cell itself, otherwise a modality key."""
    out = []
    for g, sets in grupos.items():
        for s in SETS:
            c = sets.get(s)
            if c is None:
                continue
            out.append((g, s, ""))
            out += [(g, s, x) for x in sorted(c.get("por_modalidad") or {})]
    return out


def scalars(cid: tuple[str, str, str]) -> list[str]:
    """Metrics a cell publishes: plans (P), cotizantes (C) and, for 'todos', cargas (K)."""
    return ["P", "C", "K"] if cid[1] == "todos" and not cid[2] else ["P", "C"]


def value(grupos: dict, cid: tuple[str, str, str], metric: str):
    g, s, x = cid
    c = grupos[g][s]
    if x:
        c = (c.get("por_modalidad") or {}).get(x) or {}
    return c.get({"P": "planes", "C": "cotizantes", "K": "cargas"}[metric])


class Table:
    def __init__(self, grupos: dict, members: dict[str, list[str]]):
        self.grupos = grupos
        self.mods = sorted({x for sets in grupos.values() for c in sets.values() if isinstance(c, dict)
                            for x in (c.get("por_modalidad") or {})})
        isas = sorted(g.split(":", 1)[1] for g in grupos if g.startswith("isapre:"))
        self.members = {f"isapre:{i}": [i] for i in isas}
        self.members["sistema"] = isas
        for g in ("abiertas", "cerradas"):
            self.members[g] = [str(i) for i in members.get(g) or []]
        self.atoms = {a: n for n, a in enumerate((i, cm, cp, m) for i in isas for cm in COMERS for cp in (0, 1) for m in self.mods)}
        self.cells = [c for c in cell_ids(grupos) if c[0] in self.members]

    def vector(self, cid: tuple[str, str, str], metric: str) -> set[int]:
        g, s, x = cid
        cm, cp = SETS[s]
        ids = set(self.members[g])
        return {n for (i, a_cm, a_cp, m), n in self.atoms.items()
                if i in ids and (cm is None or a_cm == cm) and (cp is None or a_cp == cp) and (not x or m == x)
                and (metric == "P" or a_cp == 1)}  # cotizantes and cargas live only in plans with cotizantes

    def leaks(self, hidden: set, sensitive: set | None = None) -> list[tuple]:
        """Sensitive hidden (cell, metric) whose value can be recovered from the published cells.

        Only the small cells (and the splits of a small cell) are sensitive: a complementary cell that can be
        recovered adds nothing to the span, so it cannot help recover a small one."""
        sensitive = hidden if sensitive is None else sensitive
        out = []
        for metric in ("P", "C", "K"):
            pub = [c for c in self.cells if c not in hidden and metric in scalars(c)]
            zero: set[int] = set()
            for c in self.cells:
                if c in hidden:
                    continue
                if value(self.grupos, c, "P") == 0 or (metric in scalars(c) and value(self.grupos, c, metric) == 0):
                    zero |= self.vector(c, "P" if value(self.grupos, c, "P") == 0 else metric)
            sp = Span()
            for c in pub:
                v = self.vector(c, metric) - zero
                if v:
                    sp.add(dict.fromkeys(v, 1))
            totals = [self.vector(c, metric) - zero for c in pub if c[1] == "todos" and not c[2]]
            for c in self.cells:
                if c in hidden and c in sensitive and metric in scalars(c):
                    v = self.vector(c, metric) - zero
                    # Cotizantes of 'vigentes' equal the Isapre total by definition: public, not a leak.
                    if v and v not in totals and sp.contains(dict.fromkeys(v, 1)):
                        out.append((c, metric))
        return out


SALE_SETS = ("venta", "no_venta", "cerrados_con_cotizantes")


def level_cells(table: Table, group: str, level: int) -> set:
    """Cells hidden for an Isapre at a protection level.

    1: modality splits of the sale sets (on sale, not on sale, not on sale with cotizantes);
    2: every modality split;  3: everything except the Isapre total ('todos'), which is reconciled with the SIS cartera.
    """
    g = group
    cells = [c for c in table.cells if c[0] == g]
    if level <= 0:
        return set()
    if level == 1:
        return {c for c in cells if c[2] and c[1] in SALE_SETS}
    if level == 2:
        return {c for c in cells if c[2]}
    return {c for c in cells if c != (g, "todos", "")}


def group_cells(table: Table) -> set:
    """The closed group and the system publish only their total: a difference of groups would isolate an Isapre."""
    return {c for c in table.cells if c[0] in ("cerradas", "sistema") and c != (c[0], "todos", "")}


def protect(grupos: dict, members: dict[str, list[str]], types: dict[str, str], max_rounds: int = 60) -> dict:
    """Hide cells with 1-4 plans and enough complementary cells that no hidden count can be recovered.

    Row rule per Isapre (levels in ``level_cells``): a small modality split raises the Isapre to level 1 (2 if the
    split is in 'todos' or 'vigentes'); a small set raises it to 3. Among open Isapres a raised level never stands
    alone (the open total would give it back), so the smallest other open Isapre is raised with it. The exact check
    then runs; while a hidden count is still recoverable, the Isapre holding it (or the smallest open one) is raised
    one level. Returns {cell: reason}; raises if the Isapre total itself would have to be hidden.
    """
    t = Table(grupos, members)
    isas = t.members["sistema"]
    size = {i: value(grupos, (f"isapre:{i}", "todos", ""), "P") or 0 for i in isas}
    level = {f"isapre:{i}": 0 for i in isas}
    level["abiertas"] = 0  # last resort: the open group itself (the ficha then HOLDs for lack of figures)
    primary = set()
    for c in t.cells:
        n = value(grupos, c, "P")
        if n is None or not 1 <= n < MIN_PLANS:
            continue
        primary.add(c)
        if not c[2]:  # its modality splits too: a zero beside a hidden small cell tells the modality of its plans
            primary |= {x for x in t.cells if x[0] == c[0] and x[1] == c[1]}
        if c[0] not in level:
            continue
        if c[1] == "todos" and not c[2]:
            raise ValueError(f"total below the minimum: {c}")
        need = 3 if not c[2] else 1 if c[1] in SALE_SETS else 2
        level[c[0]] = max(level[c[0]], need)

    def pair_open() -> None:
        opened = [f"isapre:{i}" for i in isas if types.get(i) == "open"]
        for lv in (1, 2, 3):
            at = [i for i in opened if level[i] >= lv]
            if len(at) == 1 and level["abiertas"] < lv:
                rest = sorted((i for i in opened if level[i] < lv), key=lambda i: (size[i.split(":")[1]], i))
                if rest:
                    level[rest[0]] = lv

    def hidden_now() -> dict:
        h: dict = {}
        for g, lv in level.items():
            for c in level_cells(t, g, lv):
                h[c] = PRIMARY if c in primary else COMPLEMENTARY
        for c in group_cells(t):
            h[c] = PRIMARY if c in primary else COMPLEMENTARY
        for c in primary:
            h.setdefault(c, PRIMARY)
        return h

    for _ in range(max_rounds):
        pair_open()
        h = hidden_now()
        leaks = t.leaks(set(h), primary)
        if not leaks:
            return h
        c = leaks[0][0]
        g = c[0] if c[0] in level and level[c[0]] < 3 else None
        if g is None:
            cand = sorted((f"isapre:{j}" for j in isas if types.get(j) == "open" and level[f"isapre:{j}"] < 3),
                          key=lambda j: (level[j], size[j.split(":")[1]], j))
            g = cand[0] if cand else "abiertas" if level["abiertas"] < 3 else None
            if g is None:
                raise ValueError(f"cannot protect {c}")
        level[g] += 1
    raise ValueError("small-cell protection did not converge")


def apply(grupos: dict, hidden: dict) -> None:
    """Blank the hidden cells in place; the reason stays in 'suprimido'."""
    for (g, s, x), why in hidden.items():
        c = grupos[g][s]
        if x:
            c["por_modalidad"][x] = {"planes": None, "cotizantes": None, "suprimido": why}
            continue
        for k in ("planes", "cotizantes", "cargas"):
            if k in c:
                c[k] = None
        if isinstance(c.get("precio_uf"), dict):
            c["precio_uf"] = {"mediana": None, "p25": None, "p75": None, "mediana_pond": None, "suprimido": why}
        c["suprimido"] = why


def check(pl: dict) -> list[str]:
    """Reader-side check of a published planes aggregate: no cell with 1-4 plans, nothing hidden is recoverable."""
    g = pl.get("grupos") or {}
    sup = pl.get("supresion") or {}
    if not sup.get("miembros"):
        return ["disclosure_check_missing"]
    t = Table(g, sup["miembros"])
    f = []
    hidden, small = set(), set()
    for c in t.cells:
        n = value(g, c, "P")
        if n is None:
            hidden.add(c)
            node = g[c[0]][c[1]] if not c[2] else (g[c[0]][c[1]].get("por_modalidad") or {}).get(c[2]) or {}
            if node.get("suprimido") != COMPLEMENTARY:
                small.add(c)
        elif 1 <= n < MIN_PLANS:
            f.append(f"small_cell_published:{'/'.join(x for x in c if x)}")
    f += [f"small_cell_recoverable:{'/'.join(x for x in c if x)}:{m}" for c, m in t.leaks(hidden, small)]
    return f
