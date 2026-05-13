---
name: ontology-sparql-endpoint
description: Deploys a SPARQL 1.1 query+update endpoint with YASGUI web UI using pyoxigraph. Use when you need to explore, query, or share an ontology via HTTP without setting up a triple store.
license: MIT
compatibility: Requires python3, rdflib, pyoxigraph
---

# Ontology SPARQL Endpoint

Deploy a fully functional SPARQL 1.1 endpoint from any RDF repository. Uses
**pyoxigraph** (Python bindings for the Oxigraph graph database) for storage
and querying, and Python's built-in HTTP server for the endpoint.

**Single script:** `scripts/deploy_endpoint.py`

## Features

- **SPARQL 1.1 Query** — `SELECT`, `ASK`, `CONSTRUCT`, `DESCRIBE`
- **SPARQL 1.1 Update** — `INSERT DATA`, `DELETE DATA`, `DELETE/INSERT`
- **YASGUI Web UI** — point your browser to `http://localhost:7878/`
- **Persistent storage** — data survives restarts (RocksDB-backed)
- **Bulk load** — merges all RDF files with rdflib, loads via N-Triples
- **Add data via HTTP** — `POST /store` with Turtle/N-Triples/RDF-XML

## Setup

```bash
cd <your-ontology-repo>
python3 -m venv .venv
source .venv/bin/activate

pip install rdflib pyoxigraph
```

> `pyoxigraph` is a pre-compiled Python wheel — no Rust toolchain, no Java, no binary downloads needed.

## Usage

### Load data and start endpoint

```bash
python scripts/deploy_endpoint.py . --port 7878
```

This merges all RDF files, bulk-loads them, and starts the HTTP server.

### Just load data (no server)

```bash
python scripts/deploy_endpoint.py . --no-serve --data-dir oxigraph_data/
```

### Serve existing data without reloading

```bash
python scripts/deploy_endpoint.py . --serve-only --data-dir oxigraph_data/
```

### Query examples

```bash
# SELECT via curl
curl -X POST http://localhost:7878/query \
  -H 'Content-Type: application/sparql-query' \
  --data 'SELECT * WHERE { ?s ?p ?o } LIMIT 10'

# ASK
curl -X POST http://localhost:7878/query \
  -H 'Content-Type: application/sparql-query' \
  --data 'ASK WHERE { ?s a <http://example.com/skos#Concept> }'

# CONSTRUCT (returns Turtle)
curl -X POST http://localhost:7878/query \
  -H 'Content-Type: application/sparql-query' \
  --data 'CONSTRUCT WHERE { ?s ?p ?o } LIMIT 5'
```

### Add data via HTTP

```bash
curl -X POST http://localhost:7878/store \
  -H 'Content-Type: text/turtle' -T new_data.ttl
```

### SPARQL Update

```bash
curl -X POST http://localhost:7878/update \
  -H 'Content-Type: application/sparql-update' \
  --data 'INSERT DATA { <http://example.com/s> <http://example.com/p> "hello"@en }'
```

## Architecture

```
┌─────────────────────┐
│  RDF files in repo  │
│  (.ttl, .owl, …)    │
└────────┬────────────┘
         │ rdflib merge + N-Triples serialize
         ▼
┌─────────────────────┐
│  pyoxigraph Store    │
│  (RocksDB on disk)  │
└────────┬────────────┘
         │ Python http.server
         ▼
┌─────────────────────┐
│  HTTP SPARQL endpoint│
│  /query  — SELECT,  │
│           ASK,       │
│           CONSTRUCT  │
│  /update — SPARQL    │
│           Update     │
│  /store  — Graph     │
│           Store      │
│  /       — YASGUI    │
└─────────────────────┘
```

## Limitations

- **Not production-hardened.** Python's `http.server` is single-threaded. For
  production, use the [Oxigraph CLI](https://github.com/oxigraph/oxigraph)
  binary (`oxigraph serve --location oxigraph_data/`), which is multi-threaded
  and includes the full SPARQL 1.1 Protocol with content negotiation.

- **No authentication.** The endpoint is open. Add a reverse proxy (nginx)
  for authentication in production.

- **Graph Store protocol is partial.** Only `POST /store` is implemented
  (add data). No `GET /store?graph=` (retrieve by graph) yet.

## Scaling Up

For production or large datasets (> 100K triples), use the native Oxigraph
binary instead of the Python wrapper:

```bash
# Install once
cargo install oxigraph-cli
# or download from https://github.com/oxigraph/oxigraph/releases

# Load data
oxigraph load --location oxigraph_data/ --file merged.nt

# Serve (multi-threaded, full protocol)
oxigraph serve --location oxigraph_data/ --bind 0.0.0.0:7878
```
