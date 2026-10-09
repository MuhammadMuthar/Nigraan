"""Relationship graph (section 6.4).

Nodes: vendors, employees, users, bank-account hashes, phones, normalised addresses, CNIC hashes.
Edges carry validity windows so a payment only sees links that existed when it was created.
Signal (0-1) + the path as evidence, e.g. Vendor "Ali Enterprises" -> phone 0300-xxx -> employee "Imran (Purchase)".
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx
import pandas as pd

from app.services.identity import norm_phone
from app.services.ledger import Ledger

FAR_FUTURE = pd.Timestamp("2100-01-01").value

# identifier kind -> (weight if shared with an employee, weight if shared with another vendor)
WEIGHTS = {"bank": (1.0, 0.6), "cnic": (1.0, 0.6), "phone": (0.9, 0.3), "address": (0.75, 0.15)}
CREATOR_LINK = 1.0
DISCLOSED_FACTOR = 0.2  # link to a vendor in the related-party register: shown, but down-weighted
KIND_LABEL = {"bank": "bank account", "cnic": "CNIC", "phone": "phone", "address": "address"}


def _ns(x) -> int | None:
    return None if x is None or pd.isna(x) else pd.Timestamp(x).value


def _mask_phone(p: str) -> str:
    d = norm_phone(p)
    return f"{d[:4]}-xxx{d[-4:]}" if len(d) >= 8 else d


@dataclass
class GraphResult:
    signal: float = 0.0
    links: list[dict] = field(default_factory=list)  # strongest first
    path: list[dict] = field(default_factory=list)  # nodes of the strongest path


class RelationGraph:
    def __init__(self, L: Ledger):
        G = nx.Graph()
        self.G = G
        self.emp_user = {}
        for u in L.users.itertuples(index=False):
            if not pd.isna(u.employee_id):
                self.emp_user[int(u.employee_id)] = (int(u.id), u.name, u.role)
        self.user_emp = {uid: eid for eid, (uid, _, _) in self.emp_user.items()}
        for e in L.employees.itertuples(index=False):
            n = f"employee:{e.id}"
            G.add_node(n, kind="employee", label=f"{e.name} ({e.department})", since=_ns(e.hire_date))
            for kind, val, label in (("bank", e.bank_hash, f"bank ••{e.bank_last4}"), ("cnic", e.cnic_hash, "CNIC"),
                                     ("phone", norm_phone(e.phone), _mask_phone(e.phone)),
                                     ("address", e.address_norm, e.address)):
                if val:
                    idn = f"{kind}:{val}"
                    G.add_node(idn, kind=kind, label=label)
                    G.add_edge(n, idn, since=_ns(e.hire_date), until=FAR_FUTURE)
        self.vendor_name = {}
        self.vendor_creator = {}
        self.disclosed = {}
        for v in L.vendors.itertuples(index=False):
            n = f"vendor:{v.id}"
            self.vendor_name[int(v.id)] = v.name
            if isinstance(v.related_party_note, str) and v.related_party_note:
                self.disclosed[int(v.id)] = v.related_party_note
            self.vendor_creator[int(v.id)] = None if pd.isna(v.created_by) else int(v.created_by)
            since = _ns(v.created_at)
            G.add_node(n, kind="vendor", label=v.name, since=since)
            for kind, val, label in (("phone", norm_phone(v.phone), _mask_phone(v.phone)),
                                     ("address", v.address_norm, v.address), ("cnic", v.owner_cnic_hash, "CNIC")):
                if val and not pd.isna(val):
                    idn = f"{kind}:{val}"
                    if idn not in G:
                        G.add_node(idn, kind=kind, label=label)
                    G.add_edge(n, idn, since=since, until=FAR_FUTURE)
        for a in L.accounts.itertuples(index=False):
            n = f"vendor:{a.vendor_id}"
            idn = f"bank:{a.iban_hash}"
            if idn not in G:
                G.add_node(idn, kind="bank", label=f"bank ••{a.iban_last4}")
            until = _ns(a.valid_to) or FAR_FUTURE
            if G.has_edge(n, idn):  # account re-activated later: widen the window
                e = G.edges[n, idn]
                e["windows"] = e.get("windows", [(e["since"], e["until"])]) + [(_ns(a.valid_from), until)]
            else:
                G.add_edge(n, idn, since=_ns(a.valid_from), until=until)

    @staticmethod
    def _valid(edge: dict, t: int) -> bool:
        for s, u in edge.get("windows", [(edge["since"], edge["until"])]):
            if (s is None or s <= t) and t < u:
                return True
        return False

    def links_for(self, vendor_id: int, t: int) -> GraphResult:
        G = self.G
        vn = f"vendor:{vendor_id}"
        if vn not in G:
            return GraphResult()
        creator = self.vendor_creator.get(vendor_id)
        creator_emp = self.user_emp.get(creator) if creator else None
        links = []
        for idn in G.neighbors(vn):
            if not self._valid(G.edges[vn, idn], t):
                continue
            kind = G.nodes[idn]["kind"]
            for other in G.neighbors(idn):
                if other == vn or not self._valid(G.edges[idn, other], t):
                    continue
                okind = G.nodes[other]["kind"]
                since = G.nodes[other].get("since")
                if since is not None and since > t:
                    continue
                if okind == "employee":
                    eid = int(other.split(":")[1])
                    w = WEIGHTS[kind][0]
                    path = [
                        {"id": vn, "kind": "vendor", "label": G.nodes[vn]["label"]},
                        {"id": idn, "kind": kind, "label": G.nodes[idn]["label"]},
                        {"id": other, "kind": "employee", "label": G.nodes[other]["label"]},
                    ]
                    text = f'Vendor shares {KIND_LABEL[kind]} with employee {G.nodes[other]["label"]}'
                    if creator_emp == eid:
                        w = CREATOR_LINK
                        uid, uname, _ = self.emp_user[eid]
                        path.append({"id": f"user:{uid}", "kind": "user", "label": f"{uname} (created this vendor)"})
                        text = f"Vendor was created by {uname}, who shares its {KIND_LABEL[kind]}"
                    disclosed = self.disclosed.get(vendor_id)
                    if disclosed:
                        w *= DISCLOSED_FACTOR
                        text = f"{text} ({disclosed})"
                    links.append({"weight": w, "kind": kind, "target": "employee", "text": text, "path": path,
                                  "disclosed": bool(disclosed)})
                elif okind == "vendor":
                    w = WEIGHTS[kind][1]
                    path = [
                        {"id": vn, "kind": "vendor", "label": G.nodes[vn]["label"]},
                        {"id": idn, "kind": kind, "label": G.nodes[idn]["label"]},
                        {"id": other, "kind": "vendor", "label": G.nodes[other]["label"]},
                    ]
                    links.append({"weight": w, "kind": kind, "target": "vendor", "path": path,
                                  "text": f'Shares {KIND_LABEL[kind]} with another vendor, {G.nodes[other]["label"]}'})
        links.sort(key=lambda x: -x["weight"])
        if not links:
            return GraphResult()
        return GraphResult(signal=links[0]["weight"], links=links[:5], path=links[0]["path"])

    def neighbourhood(self, vendor_id: int, t: int, hops: int = 2) -> dict:
        """Nodes/edges around a vendor for the case screen (valid at time t)."""
        G = self.G
        vn = f"vendor:{vendor_id}"
        if vn not in G:
            return {"nodes": [], "edges": []}
        nodes, edges = {vn}, []
        frontier = [vn]
        for _ in range(hops):
            nxt = []
            for n in frontier:
                for m in G.neighbors(n):
                    if not self._valid(G.edges[n, m], t):
                        continue
                    edges.append((n, m))
                    if m not in nodes:
                        nodes.add(m)
                        nxt.append(m)
            frontier = nxt
        # keep identifier nodes only if they connect at least two entities
        deg = {}
        for a, b in edges:
            deg[a] = deg.get(a, 0) + 1
            deg[b] = deg.get(b, 0) + 1
        keep = {n for n in nodes if G.nodes[n]["kind"] in ("vendor", "employee", "user") or deg.get(n, 0) >= 2 or n == vn}
        keep |= {b for a, b in edges if a == vn}
        return {
            "nodes": [{"id": n, "kind": G.nodes[n]["kind"], "label": G.nodes[n]["label"]} for n in sorted(keep)],
            "edges": [{"source": a, "target": b} for a, b in {tuple(sorted(e)) for e in edges} if a in keep and b in keep],
        }
