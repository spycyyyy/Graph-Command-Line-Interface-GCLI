"""
graph_cli.py
============

Interactive CLI for an multi-graph with optional clustering.

Highlights
----------

1.  CRUD commands for nodes, edges and clusters.
2.  Cluster isolation (`cluster iso <name>`).
3.  Cluster-scoped commands:
        <cluster> node … / edge …
4.  Neighbour info:
        node nbr <id>    – list neighbours
        node n   <id>    – number of neighbours
5.  Path search:
        node allp <src> <dst>   – list *all* simple paths
        node p    <src> <dst>   – shortest path (fewest nodes)
6.  CSV importer:
        cluster open <file.csv> <clusterName>
    The CSV file must contain an adjacency matrix (see help text).
7.  “Rich” fixed-frame UI: header & last output panel stay in place.
8.  No type annotations (as requested).

"""

# -----------------------------------------------------------------------------
#  Rich UI imports
# -----------------------------------------------------------------------------
import csv
import time
from collections import defaultdict, deque

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich.align import Align
from rich.theme import Theme

# -----------------------------------------------------------------------------
#  Fixed-frame REPL base class
# -----------------------------------------------------------------------------
class FixedFrameCLI:
    """
    Handles:
        • A persistent top header  (shows current view / cluster)
        • A persistent output panel (shows last command result)
        • Clearing & redrawing the screen for every command
    """

    def __init__(self):

        # Rich theme for colour names used in markup
        self.console = Console(theme=Theme({
            "prompt":  "bold cyan",
            "title":   "bold blue",
            "panel":   "bold green",
            "border":  "magenta",
            "exit":    "green",
            "error":   "bold red",
            "time":    "italic yellow",
        }))

        self.running = True          # set to  False  to leave main loop
        self.last_panel = None       # Rich Panel that holds last result

    # ────────────────── drawing helpers ──────────────────────────────
    def _draw_frame(self, active_view):
        """Redraw header + last output panel (fixed layout)."""
        self.console.clear()

        # Header bar
        self.console.rule(f"[title]Graph Visualizer (view: {active_view})[/title]",align="center")
        self.console.print()

        # Body panel (last command result or welcome)
        self.console.print(
            self.last_panel or
            Panel("Welcome!  Type commands or 'help'.",
                    title="[panel]Output[/panel]",
                    border_style="border",
                    subtitle="└─ End ─┘",
                    subtitle_align="right",
                    padding=(1, 2))
        )
        self.console.print()   # blank line above input prompt

    def _make_panel(self, content, elapsed=0.0):
        """Return a Rich Panel with elapsed-time footer."""
        body = Columns(
            [Text.from_ansi(content),Align(Text(f"Processing time: {elapsed:.6f}s", style="time"),align="right")],
            expand=True)
        return Panel(body,
                        title="[panel]Output[/panel]",
                        border_style="border",
                        subtitle="└─ End ─┘",
                        subtitle_align="right",
                        padding=(1, 2))

    # ────────────────── REPL main loop ───────────────────────────────
    def start(self):
        while self.running:
            self._draw_frame(self.header_name())

            try:
                cmd = self.console.input("[prompt]>>> [/prompt]").strip()
                if not cmd:
                    continue
                if cmd.lower() in {"exit", "quit", "q"}:
                    self.console.print("\n[exit]Exiting… Goodbye![/exit]")
                    time.sleep(1)
                    break

                t0 = time.perf_counter()
                out = self.handle(cmd)                      # delegate
                self.last_panel = self._make_panel(out,time.perf_counter() - t0)

            except KeyboardInterrupt:
                self.last_panel = self._make_panel("[error]Interrupted[/error]")
            except Exception as exc:                         # pragma: no cover
                self.last_panel = self._make_panel(f"[ERROR] {exc}")

    # implemented by subclass
    def header_name(self): ...
    def handle(self, cmd): ...


# -----------------------------------------------------------------------------
#  Graph CLI implementation
# -----------------------------------------------------------------------------
class GraphCLI(FixedFrameCLI):

    # automatic “global” cluster that always exists
    DEFAULT_CLUSTER = "_all_"

    # in-memory graph --------------------------------------------------
    #   self.nodes     : { int nodeId        -> string value }
    #   self.edges     : { "i_j_eid"         -> string value }
    #   self.clusters  : { str clusterName   -> {'nodes': set(int),
    #                                            'value': str   } }
    # Note:   an edge is directed only by its name; commands treat it as
    #         *undirected* when searching neighbours or paths.

    # -----------------------------------------------------------------
    # HELP text (displayed by command  help/h/? )
    # -----------------------------------------------------------------
    HELP_TEXT = """
    ── Quick reference ──────────────────────────────────────────────────
    GLOBAL view (or current isolation)
    node list / new <id> <val> / get <id> / up <id> <val> / rmv <id>
    node nbr <id>        – list neighbour ids
    node n   <id>        – neighbour count
    node allp <s> <d>    – all simple paths
    node p    <s> <d>    – shortest path

    edge list
    edge new <i> <j> <eid> <val>      edge get <edgeName> | get <i> <j>
    edge up  <edgeName> <val>         edge up  <i> <j> <val>
    edge rmv <edgeName>

    cluster list
    cluster new <nodes…> <name> <val>
    cluster get <name>        cluster rmv <name>
    cluster iso               (leave isolation)
    cluster iso <name>        (isolate)
    cluster open <csv> <name> ← import adjacency matrix (see below)

    CLUSTER-specific commands
    <cl> node  list / new <id> / rmv <id> / get <id>
    <cl> node  nbr <id> / n <id> / allp <s> <d> / p <s> <d>
    <cl> edge  list / new / rmv / get …

    CSV importer
    The first row/column (after the blank corner cell) must list node IDs.
    Non-empty / non-zero cells create an edge with the cell’s value.

    General:   help    exit/quit
    ─────────────────────────────────────────────────────────────────────
""".strip()

    # -----------------------------------------------------------------
    # constructor  – allocate state and create the default cluster
    # -----------------------------------------------------------------
    def __init__(self):
        super().__init__()

        self.nodes = {}            # master node registry
        self.edges = {}            # master edge registry
        self.clusters = {}         # cluster registry
        self.current_view = self.DEFAULT_CLUSTER   # active isolation name

        self._sync_default_cluster()

    # -----------------------------------------------------------------
    # tiny helpers
    # -----------------------------------------------------------------
    def header_name(self):
        return self.current_view

    @staticmethod
    def make_edge_name(a, b, eid):
        """Canonical edge name  'a_b_eid'  (all ints)."""
        return f"{a}_{b}_{eid}"

    @staticmethod
    def split_edge_name(name):
        """Return (a, b)  from  'a_b_eid'.  Returns (-1,-1) on error."""
        try:
            a, b, _ = name.split("_", 2)
            return int(a), int(b)
        except ValueError:
            return -1, -1

    def _sync_default_cluster(self):
        """Refresh automatic '_all_' cluster to contain every node."""
        self.clusters[self.DEFAULT_CLUSTER] = {
            "nodes": set(self.nodes),
            "value": "All existing nodes"
        }

    # -----------------------------------------------------------------
    # visibility helpers (respect current isolation)
    # -----------------------------------------------------------------
    def visible_nodes(self):
        return (set(self.nodes) if self.current_view == self.DEFAULT_CLUSTER
                else set(self.clusters[self.current_view]["nodes"]))

    def visible_edge(self, edge_name):
        a, b = self.split_edge_name(edge_name)
        return a in self.visible_nodes() and b in self.visible_nodes()

    # -----------------------------------------------------------------
    # neighbour helpers
    # -----------------------------------------------------------------
    def neighbours_view(self, nid):
        """Neighbour ids of  nid  *in current view*."""
        out = set()
        for e in self.edges:
            if not self.visible_edge(e):
                continue
            a, b = self.split_edge_name(e)
            if a == nid:
                out.add(b)
            elif b == nid:
                out.add(a)
        return out

    def neighbours_cluster(self, cname, nid):
        """Neighbour ids of  nid  *inside explicit cluster*."""
        if cname not in self.clusters:
            return set()
        nodes = self.clusters[cname]["nodes"]
        out = set()
        for e in self.edges:
            if not self.edge_in_cluster(cname, e):
                continue
            a, b = self.split_edge_name(e)
            if a == nid:
                out.add(b)
            elif b == nid:
                out.add(a)
        return out

    # -----------------------------------------------------------------
    # path helpers  (DFS for all paths  /  BFS for shortest)
    # -----------------------------------------------------------------
    def _edge_between(self, a, b, edge_pool):
        """Return *any* edge name connecting a and b contained in edge_pool."""
        for e in edge_pool:
            x, y = self.split_edge_name(e)
            if {x, y} == {a, b}:
                return e
        return None

    def _all_paths(self, src, dst, edges_ok, nodes_ok):
        """DFS enumeration of all simple paths between src and dst."""
        graph = defaultdict(set)
        for e in edges_ok:
            a, b = self.split_edge_name(e)
            if a in nodes_ok and b in nodes_ok:
                graph[a].add(b)
                graph[b].add(a)

        paths = []
        stack = [(src, [src], [])]         # (node, node_path, edge_path)
        while stack:
            node, npath, epath = stack.pop()
            if node == dst:
                # stitch nodes + edge names  [n0,e0,n1,e1,…,nK]
                out = []
                for i, n in enumerate(npath):
                    out.append(n)
                    if i < len(epath):
                        out.append(epath[i])
                paths.append(out)
                continue
            for nbr in graph[node]:
                if nbr in npath:           # avoid cycles (simple paths)
                    continue
                ed = self._edge_between(node, nbr, edges_ok)
                stack.append((nbr, npath + [nbr], epath + [ed]))
        return paths

    def _shortest_path(self, src, dst, edges_ok, nodes_ok):
        """BFS shortest path (fewest nodes)."""
        graph = defaultdict(set)
        for e in edges_ok:
            a, b = self.split_edge_name(e)
            if a in nodes_ok and b in nodes_ok:
                graph[a].add(b)
                graph[b].add(a)

        queue = deque([(src, [src])])
        seen = {src}
        while queue:
            node, npath = queue.popleft()
            if node == dst:
                # convert node list → interleaved node/edge list
                out = []
                for i, n in enumerate(npath):
                    out.append(n)
                    if i < len(npath) - 1:
                        out.append(self._edge_between(n, npath[i + 1], edges_ok))
                return out
            for nbr in graph[node]:
                if nbr not in seen:
                    seen.add(nbr)
                    queue.append((nbr, npath + [nbr]))
        return []

    # -----------------------------------------------------------------
    # edge helpers for cluster checks
    # -----------------------------------------------------------------
    def edge_in_cluster(self, cname, ename):
        a, b = self.split_edge_name(ename)
        return a in self.clusters[cname]["nodes"] and b in self.clusters[cname]["nodes"]

    # -----------------------------------------------------------------
    # pretty edge list formatter
    # -----------------------------------------------------------------
    @staticmethod
    def fmt_edges(ed):
        grouped = defaultdict(list)
        for n, v in ed.items():
            try:
                i, j, eid = map(int, n.split("_"))
            except ValueError:
                continue
            grouped[(i, j)].append((eid, v))

        if not grouped:
            return "[INFO] no edges"

        lines = []
        checked = []
        for (i, j), items in sorted(grouped.items()):
            items.sort()
            inside = " , ".join(f"{eid}: {val}" for eid, val in items)
            if i not in checked:
                lines.append(f"{i} -> {j}: [ {inside} ]")
                checked.append(i)
            else:
                lines.append(f"-> {j}: [ {inside} ]")
        return "\n".join(lines)

    # -----------------------------------------------------------------
    # CSV adjacency-matrix importer (cluster open)
    # -----------------------------------------------------------------
    def _next_eid(self, a, b):
        """Return next free edge-id between a and b."""
        m = 0
        for k in self.edges:
            x, y, eid = k.split("_")
            if {int(x), int(y)} == {a, b}:
                m = max(m, int(eid))
        return m + 1

    def import_csv_matrix(self, file_path, cluster_name):
        """
        Read CSV adjacency matrix and create a fresh cluster.
        Format (commas):
            ,1,2,3
            1,,a,
            2,7,,b
            3,,4,
        Non-empty / non-zero cells create edges with the cell text as value.
        New nodes receive the value '(csv)'.
        """
        try:
            with open(file_path, newline="") as fh:
                rows = list(csv.reader(fh))
        except Exception as exc:
            return f"[ERROR] cannot open file: {exc}"

        if not rows or len(rows[0]) < 2:
            return "[ERROR] invalid matrix format"

        col_ids = [int(x) for x in rows[0][1:]]     # header row
        row_ids = [int(r[0]) for r in rows[1:]]     # header column

        added_nodes = 0
        added_edges = 0

        # ensure nodes exist
        for nid in set(col_ids + row_ids):
            if nid not in self.nodes:
                self.nodes[nid] = nid
                added_nodes += 1

        # new cluster
        if cluster_name in self.clusters:
            return "[ERROR] cluster already exists"
        self.clusters[cluster_name] = {
            "nodes": set(col_ids),
            "value": f"CSV:{file_path}"
        }

        # parse matrix cells
        for r_idx, rid in enumerate(row_ids):
            row_cells = rows[r_idx + 1][1:]
            for c_idx, cell in enumerate(row_cells):
                if cell.strip() == "" or cell.strip() == "0":
                    continue
                cid = col_ids[c_idx]
                eid = self._next_eid(rid, cid)
                en = self.make_edge_name(rid, cid, eid)
                self.edges[en] = cell.strip()
                added_edges += 1

        self._sync_default_cluster()
        return (f"Imported {added_nodes} node(s) and {added_edges} edge(s) "
                f"into cluster '{cluster_name}'.")

    # -----------------------------------------------------------------
    # helper for edge-identifier parsing
    # -----------------------------------------------------------------
    @staticmethod
    def parse_edge_id(tokens):
        """
        Accept   [name]   or   <i> <j> <eid>
        Return (edge_name, error_msg)
        """
        if len(tokens) == 3 and all(x.isdigit() for x in tokens):
            return GraphCLI.make_edge_name(int(tokens[0]),int(tokens[1]),int(tokens[2])), ""
        if len(tokens) == 1: return tokens[0], ""
        return "", "[ERROR] invalid edge identifier"

    # =========================================================================
    #                            COMMAND DISPATCHER
    # =========================================================================
    def handle(self, cmd):
        """Top-level dispatcher routing to appropriate handler."""
        toks = cmd.split()
        if not toks:
            return "[ERROR] empty command"

        # --- built-in help -------------------------------------------
        if toks[0].lower() in {"help", "h", "?"}:
            return self.HELP_TEXT

        # --- cluster-scoped commands  <cluster> node|edge ... --------
        if len(toks) >= 3 and toks[1].lower() in {"node", "edge"}:
            cname = toks[0]
            if toks[1].lower() == "node":
                return self._cluster_node(cname, toks[2:])
            return self._cluster_edge(cname, toks[2:])

        # --- global categories ---------------------------------------
        cat = toks[0].lower()
        if cat in {"n", "node"}:      return self._node(toks[1:])
        if cat in {"e", "edge"}:      return self._edge(toks[1:])
        if cat in {"c", "cluster"}:   return self._cluster(toks[1:])
        return "[ERROR] unknown command category"

    # =========================================================================
    #                GLOBAL  NODE  COMMANDS
    # =========================================================================
    def _node(self, toks):
        if not toks:
            return "[ERROR] node sub-command missing"
        sub = toks[0].lower()
        view_nodes = self.visible_nodes()

        # ------ list --------------------------------------------------
        if sub == "list":
            if not view_nodes:
                return "[INFO] no nodes"
            return "\n".join(f"Node {nid}: {self.nodes[nid]}" for nid in sorted(view_nodes))

        # ------ new  --------------------------------------------------
        if sub == "new":
            if len(toks) < 3:
                return "Usage: node new <id> <value>"
            nid = int(toks[1])
            if nid in self.nodes:
                return "[ERROR] node exists"
            self.nodes[nid] = " ".join(toks[2:])
            self._sync_default_cluster()
            # auto-add to isolated view
            if self.current_view != self.DEFAULT_CLUSTER:
                self.clusters[self.current_view]["nodes"].add(nid)
            return f"Node {nid} added."

        # ------ get ---------------------------------------------------
        if sub == "get":
            if len(toks) != 2:
                return "Usage: node get <id>"
            nid = int(toks[1])
            if nid not in view_nodes: return "[ERROR] node not in current view"
            return self.nodes[nid]

        # ------ up ----------------------------------------------------
        if sub == "up":
            if len(toks) < 3:
                return "Usage: node up <id> <value>"
            nid = int(toks[1])
            if nid not in view_nodes: return "[ERROR] node not in current view"
            self.nodes[nid] = " ".join(toks[2:])
            return f"Node {nid} updated."

        # ------ rmv ---------------------------------------------------
        if sub in {"rmv", "rmb"}:
            if len(toks) != 2:
                return "Usage: node rmv <id>"
            nid = int(toks[1])
            if nid not in view_nodes:
                return "[ERROR] node not in current view"
            # remove node + its edges
            del self.nodes[nid]
            self.edges = {k: v for k, v in self.edges.items() if nid not in self.split_edge_name(k)}
            #self.edges = filter(self.edges.items(), lambda item: nid not in self.split_edge_name(item[0]))
            for cl in self.clusters.values():
                cl["nodes"].discard(nid)
            self._sync_default_cluster()
            return f"Node {nid} removed."

        # ------ neighbour list ---------------------------------------
        if sub in {"nbr", "neigh", "neighbors"}:
            if len(toks) != 2:
                return "Usage: node nbr <id>"
            nid = int(toks[1])
            if nid not in view_nodes:
                return "[ERROR] node not in current view"
            nb = self.neighbours_view(nid)
            return ", ".join(map(str, sorted(nb))) or "[INFO] no neighbour"

        # ------ neighbour count --------------------------------------
        if sub == "n":
            if len(toks) != 2:
                return "Usage: node n <id>"
            nid = int(toks[1])
            if nid not in view_nodes:
                return "[ERROR] node not in current view"
            return str(len(self.neighbours_view(nid)))

        # ------ all paths --------------------------------------------
        if sub == "allp":
            if len(toks) != 3: return "Usage: node allp <src> <dst>"
            src, dst = map(int, toks[1:3])
            if src not in view_nodes or dst not in view_nodes:
                return f"[ERROR] nodes {src} /  nodes {dst} not in current view"
            paths = self._all_paths(src, dst,list(filter(self.visible_edge,self.edges)),view_nodes)
            return "\n".join(f"{len(p)//2} : {p}" for p in sorted(paths, key= len)) or f"[INFO] no path from {src} -> {dst}"

        # ------ shortest path ----------------------------------------
        if sub == "p":
            if len(toks) != 3: return "Usage: node p <src> <dst>"
            src, dst = map(int, toks[1:3])
            if src not in view_nodes or dst not in view_nodes:
                return f"[ERROR] nodes {src} /  nodes {dst} not in current view"
            #path = self._shortest_path(src, dst,{e for e in self.edges if self.visible_edge(e)} ,view_nodes)
            path = self._shortest_path(src, dst,list(filter(self.visible_edge,self.edges)),view_nodes)

            return str(path) if path else f"[INFO] no path from {src} -> {dst}"

        return "[ERROR] unknown node sub-command"

    # =========================================================================
    #                GLOBAL  EDGE  COMMANDS
    # =========================================================================
    def _edge(self, toks):
        if not toks:
            return "[ERROR] edge sub-command missing"
        sub = toks[0].lower()
        view_nodes = self.visible_nodes()

        # ------ list --------------------------------------------------
        if sub == "list":
            return self.fmt_edges({k: v for k, v in self.edges.items() if self.visible_edge(k)})

        # ------ new ---------------------------------------------------
        if sub == "new":
            if len(toks) < 5 or not all(x.isdigit() for x in toks[1:4]):
                return "Usage: edge new <id1> <id2> <eid> <value>"
            i, j, eid = map(int, toks[1:4])
            if i not in view_nodes or j not in view_nodes:
                return "[ERROR] nodes must be in current view"
            name = self.make_edge_name(i, j, eid)
            if name in self.edges:
                return "[ERROR] edge exists"
            self.edges[name] = " ".join(toks[4:])
            return f"Edge {name} added."

        # ------ get ---------------------------------------------------
        if sub == "get":
            # by node pair
            if len(toks) == 3 and all(x.isdigit() for x in toks[1:3]):
                i, j = map(int, toks[1:3])
                if i not in view_nodes or j not in view_nodes:
                    return "[ERROR] nodes not in current view"
                eds = {k: v for k, v in self.edges.items()
                       if {i, j} == set(self.split_edge_name(k))}
                return str(eds or "[INFO] no edge")
            # by name
            ident, err = self.parse_edge_id(toks[1:2])
            if err:
                return err
            if ident not in self.edges:
                return "[ERROR] edge not found"
            if not self.visible_edge(ident):
                return "[ERROR] edge not in current view"
            return self.edges[ident]

        # ------ rmv ---------------------------------------------------
        if sub in {"rmv", "rmb"}:
            ident, err = self.parse_edge_id(toks[1:])
            if err:
                return err
            if ident not in self.edges:
                return "[ERROR] edge not found"
            if not self.visible_edge(ident):
                return "[ERROR] edge not in current view"
            del self.edges[ident]
            return f"Edge {ident} removed."

        # ------ up ----------------------------------------------------
        if sub == "up":
            # form   id1 id2  update-all-between
            if len(toks) >= 4 and all(toks[1+k].isdigit() for k in (0, 1)):
                i, j = map(int, toks[1:3])
                if i not in view_nodes or j not in view_nodes:
                    return "[ERROR] nodes not in current view"
                val = " ".join(toks[3:])
                cnt = 0
                for k in list(self.edges):
                    if {i, j} == set(self.split_edge_name(k)):
                        self.edges[k] = val
                        cnt += 1
                return f"{cnt} edge(s) updated."
            # form  <edgeName> <value>
            ident, err = self.parse_edge_id(toks[1:2])
            if err:
                return err
            if len(toks) < 3:
                return "Usage: edge up <edgeName> <value>"
            if not self.visible_edge(ident):
                return "[ERROR] edge not in current view"
            self.edges[ident] = " ".join(toks[2:])
            return f"Edge {ident} updated."

        return "[ERROR] unknown edge sub-command"

    # =========================================================================
    #                GLOBAL  CLUSTER  COMMANDS
    # =========================================================================
    def _cluster(self, toks):
        if not toks:
            return "[ERROR] cluster sub-command missing"
        sub = toks[0].lower()

        # ------ OPEN  (CSV IMPORT) ------------------------------------
        if sub == "open":
            if len(toks) != 3:
                return "Usage: cluster open <csv-file> <clusterName>"
            file_path, cname = toks[1], toks[2]
            return self.import_csv_matrix(file_path, cname)

        # ------ list --------------------------------------------------
        if sub == "list":
            if not self.clusters:
                return "[INFO] no clusters"
            return "\n".join(
                f"{n}: val={d['value']} nodes={sorted(d['nodes'])}"
                for n, d in sorted(self.clusters.items()))

        # ------ new ---------------------------------------------------
        if sub == "new":
            if len(toks) < 4:
                return ("Usage: cluster new <node1> … <nodeN> "
                        "<name> <value>")
            idx, ns = 1, set()
            while idx < len(toks) and toks[idx].isdigit():
                ns.add(int(toks[idx])); idx += 1
            if not ns or idx >= len(toks) - 1:
                return ("Usage: cluster new <node1> … <nodeN> "
                        "<name> <value>")
            cname = toks[idx]
            cval = " ".join(toks[idx + 1:])
            if cname in self.clusters:
                return "[ERROR] cluster exists"
            miss = [n for n in ns if n not in self.nodes]
            if miss:
                return f"[ERROR] nodes {miss} not found"
            self.clusters[cname] = {"nodes": ns, "value": cval}
            return f"Cluster '{cname}' added."

        # ------ rmv ---------------------------------------------------
        if sub in {"rmv", "rmb"}:
            if len(toks) != 2:
                return "Usage: cluster rmv <name>"
            cname = toks[1]
            if cname in {self.DEFAULT_CLUSTER, self.current_view}:
                return "[ERROR] cannot remove default or active cluster"
            if cname not in self.clusters:
                return "[ERROR] cluster not found"
            del self.clusters[cname]
            return f"Cluster '{cname}' removed."

        # ------ get ---------------------------------------------------
        if sub == "get":
            if len(toks) != 2:
                return "Usage: cluster get <name>"
            cname = toks[1]
            if cname not in self.clusters:
                return "[ERROR] cluster not found"
            d = self.clusters[cname]
            return f"value={d['value']} nodes={sorted(d['nodes'])}"

        # ------ iso ---------------------------------------------------
        if sub == "iso":
            if len(toks) == 1:
                self.current_view = self.DEFAULT_CLUSTER
                return "Isolation cleared."
            cname = toks[1]
            if cname not in self.clusters:
                return "[ERROR] cluster not found"
            self.current_view = cname
            return f"Cluster '{cname}' isolated."

        return "[ERROR] unknown cluster sub-command"

    # =========================================================================
    #                CLUSTER-specific  NODE  COMMANDS
    # =========================================================================
    def _cluster_node(self, cname, toks):
        if cname not in self.clusters:
            return "[ERROR] cluster not found"
        if not toks:
            return ("Usage: <cluster> node list|new|rmv|get|nbr|n|allp|p …")

        sub = toks[0].lower()
        cnodes = self.clusters[cname]["nodes"]

        # ------ list --------------------------------------------------
        if sub == "list":
            if len(toks) != 1:
                return "Usage: <cluster> node list"
            if not cnodes:
                return "[INFO] no nodes in cluster"
            return "\n".join(f"{nid}: {self.nodes[nid]}"
                             for nid in sorted(cnodes))

        # ------ neighbour list ---------------------------------------
        if sub in {"nbr", "neigh", "neighbors"}:
            if len(toks) != 2:
                return "Usage: <cluster> node nbr <id>"
            nid = int(toks[1])
            if nid not in cnodes:
                return "[ERROR] node not in cluster"
            nb = self.neighbours_cluster(cname, nid)
            return ", ".join(map(str, sorted(nb))) or "[INFO] no neighbour"

        # ------ neighbour count --------------------------------------
        if sub == "n":
            if len(toks) != 2:
                return "Usage: <cluster> node n <id>"
            nid = int(toks[1])
            if nid not in cnodes:
                return "[ERROR] node not in cluster"
            return str(len(self.neighbours_cluster(cname, nid)))

        # ------ all paths --------------------------------------------
        if sub == "allp":
            if len(toks) != 3:
                return "Usage: <cluster> node allp <src> <dst>"
            src, dst = map(int, toks[1:3])
            if src not in cnodes or dst not in cnodes:
                return "[ERROR] nodes not in cluster"
            paths = self._all_paths(src, dst,
                                    {e for e in self.edges
                                     if self.edge_in_cluster(cname, e)},
                                    cnodes)
            return "\n".join(str(p) for p in paths) or "[INFO] no path"

        # ------ shortest path ----------------------------------------
        if sub == "p":
            if len(toks) != 3:
                return "Usage: <cluster> node p <src> <dst>"
            src, dst = map(int, toks[1:3])
            if src not in cnodes or dst not in cnodes:
                return "[ERROR] nodes not in cluster"
            path = self._shortest_path(src, dst,{e for e in self.edges if self.edge_in_cluster(cname, e)},cnodes)
            return str(path) if path else "[INFO] no path"

        # ------ new / rmv / get  (membership) ------------------------
        if len(toks) != 2:
            return "Usage: <cluster> node new|rmv|get <id>"

        nid = int(toks[1])

        if sub in {"new", "add"}:
            if cname == self.DEFAULT_CLUSTER:
                return "[ERROR] cannot modify default cluster"
            if nid not in self.nodes:
                return "[ERROR] node not found globally"
            if nid in cnodes:
                return "[INFO] node already in cluster"
            cnodes.add(nid)
            return f"Node {nid} added to cluster '{cname}'."

        if sub in {"rmv", "rmb", "remove"}:
            if cname == self.DEFAULT_CLUSTER:
                return "[ERROR] cannot modify default cluster"
            if nid not in cnodes:
                return "[ERROR] node not in cluster"
            cnodes.remove(nid)
            return f"Node {nid} removed from cluster '{cname}'."

        if sub == "get":
            if nid not in cnodes:
                return "[ERROR] node not in cluster"
            return self.nodes[nid]

        return "[ERROR] unknown sub-command"

    # =========================================================================
    #                CLUSTER-specific  EDGE  COMMANDS
    # =========================================================================
    def _cluster_edge(self, cname, toks):
        if cname not in self.clusters:
            return "[ERROR] cluster not found"
        if not toks:
            return ("Usage: <cluster> edge list|new|rmv|get …")
        sub = toks[0].lower()

        # ------ list --------------------------------------------------
        if sub == "list":
            if len(toks) != 1:
                return "Usage: <cluster> edge list"
            return self.fmt_edges({k: v for k, v in self.edges.items()
                                   if self.edge_in_cluster(cname, k)})

        # ------ new ---------------------------------------------------
        if sub == "new":
            if len(toks) < 5 or not all(x.isdigit() for x in toks[1:4]):
                return ("Usage: <cluster> edge new <id1> <id2> <eid> <value>")
            i, j, eid = map(int, toks[1:4])
            if i not in self.clusters[cname]["nodes"] \
               or j not in self.clusters[cname]["nodes"]:
                return "[ERROR] nodes not inside cluster"
            name = self.make_edge_name(i, j, eid)
            if name in self.edges:
                return "[ERROR] edge exists"
            self.edges[name] = " ".join(toks[4:])
            return f"Edge {name} added (cluster '{cname}')."

        # ------ rmv ---------------------------------------------------
        if sub in {"rmv", "rmb"}:
            ident, err = self.parse_edge_id(toks[1:])
            if err:
                return err
            if ident not in self.edges:
                return "[ERROR] edge not found"
            if not self.edge_in_cluster(cname, ident):
                return "[ERROR] edge not inside cluster"
            del self.edges[ident]
            return f"Edge {ident} removed."

        # ------ get ---------------------------------------------------
        if sub == "get":
            # by node pair
            if len(toks) == 3 and all(x.isdigit() for x in toks[1:3]):
                i, j = map(int, toks[1:3])
                if i not in self.clusters[cname]["nodes"] \
                   or j not in self.clusters[cname]["nodes"]:
                    return "[ERROR] nodes not inside cluster"
                eds = {k: v for k, v in self.edges.items()
                       if {i, j} == set(self.split_edge_name(k))}
                eds = {k: v for k, v in eds.items()
                       if self.edge_in_cluster(cname, k)}
                return str(eds or "[INFO] no edge")
            # by name
            ident, err = self.parse_edge_id(toks[1:2])
            if err:
                return err
            if ident not in self.edges:
                return "[ERROR] edge not found"
            if not self.edge_in_cluster(cname, ident):
                return "[ERROR] edge not inside cluster"
            return self.edges[ident]

        return "[ERROR] unknown sub-command"


# -----------------------------------------------------------------------------
#  Entry point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    GraphCLI().start()