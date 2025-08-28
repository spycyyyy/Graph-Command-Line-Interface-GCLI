# Graph-Command-Line-Interface-GCLI
Interactive CLI for an multi-graph analysis with optional clustering.
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
