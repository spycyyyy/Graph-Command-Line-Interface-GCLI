# Graph-Command-Line-Interface-GCLI
Interactive CLI for an multi-graph analysis with optional clustering.

GCLI is an interactive command-line tool for multi-graph analysis with optional clustering.
It supports node and edge management, cluster isolation, neighbour and path queries, and CSV-based graph import.

## Features
* Node and Edge CRUD: Add, remove, update, and list nodes and edges.
* Neighbour Queries: List and count neighbours for any node.
* Path Search: Find all simple paths or the shortest path between two nodes.
* Clustering: Group nodes into clusters and isolate views for analysis.
* CSV Import: Import adjacency matrices from CSV files to quickly build clusters.
* Rich UI: Fixed-layout interface using rich for clear output.

# Quick reference 
## GLOBAL view (or current isolation)
* NODE
    * node list / new <id> <val> / get <id> / up <id> <val> / rmv <id>
    * node nbr <id>        – list neighbour ids
    * node n   <id>        – neighbour count
    * node allp <src> <des>    – all simple paths
    * node p    <src> <des>    – shortest path
* EDGE
    * edge list
    * edge new <i> <j> <eid> <val>      edge get <edgeName> | get <i> <j>
    * edge up  <edgeName> <val>         edge up  <i> <j> <val>
    * edge rmv <edgeName>
* CLUSTER
    * cluster list
    * cluster new <nodes…> <name> <val>
    * cluster get <name>        cluster rmv <name>
    * cluster iso               (leave isolation)
    * cluster iso <name>        (isolate)
    * cluster open <csv> <name> ← import adjacency matrix (see below)

## CSV importer
The first row/column (after the blank corner cell) must list node IDs.
Non-empty / non-zero cells create an edge with the cell’s value.

## CLUSTER-specific commands
* <cl> node  list / new <id> / rmv <id> / get <id>
* <cl> node  nbr <id> / n <id> / allp <src> <des> / p <src> <des>
* <cl> edge  list / new / rmv / get …

General:   help    exit/quit
─────────────────────────────────────────────────────────────────────
