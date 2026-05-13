#!/usr/bin/env python3
"""
deploy_endpoint.py — Deploy a SPARQL endpoint from RDF files using pyoxigraph.

Merges all RDF files with rdflib, bulk-loads into a pyoxigraph persistent Store,
and serves a SPARQL 1.1 endpoint (query + update) via Python's built-in HTTP server.

Usage:
    python deploy_endpoint.py <repo-path> [--port 7878] [--bind 0.0.0.0]
                              [--data-dir oxigraph_data/] [--no-serve]

    # Serve existing data without reloading
    python deploy_endpoint.py <repo-path> --serve-only --data-dir oxigraph_data/

    # Just load data, skip serving
    python deploy_endpoint.py <repo-path> --no-serve

Requirements:
    pip install rdflib pyoxigraph
"""
import argparse
import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from rdflib import Graph
from pyoxigraph import Store, RdfFormat

from rdf_utils import load_graph, find_rdf_files

YASGUI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SPARQL Endpoint</title>
<link href="https://cdn.jsdelivr.net/npm/@triply/yasgui/build/yasgui.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/@triply/yasgui/build/yasgui.min.js"></script>
<style>body{margin:0;padding:12px;font-family:system-ui,sans-serif;background:#f5f5f5}
.yasgui .endpointText{display:none}</style>
</head>
<body>
<h2 style="margin:0 0 8px 0">SPARQL Endpoint</h2>
<p style="color:#666;font-size:14px;margin:0 0 12px 0">
  <code>POST /query</code> &middot; <code>POST /update</code> &middot;
  <code>GET /store?default</code> &middot; <code>POST /store</code>
</p>
<div id="yasgui"></div>
<script>
Yasgui.YASGUI.defaults.yasqe.sparql.endpoint = "/query";
Yasgui.YASGUI.defaults.yasr.renderingConfig = {output: "table"};
const yasgui = new Yasgui.YASGUI(document.getElementById("yasgui"), {requestConfig: {endpoint: "/query"}});
</script>
</body>
</html>"""


def merge_and_load(repo_path: str, store: Store) -> int:
    """Parse all RDF files with rdflib, serialize as N-Triples, bulk-load into Store."""
    print(f"[INFO] Loading RDF files from {repo_path}...", file=sys.stderr)
    g, warnings = load_graph(repo_path)
    for w in warnings:
        print(f"[WARN] {w}", file=sys.stderr)

    if len(g) == 0:
        raise RuntimeError("No RDF triples loaded. Nothing to deploy.")

    print(f"[INFO] {len(g)} triples from {len(find_rdf_files(repo_path))} files.", file=sys.stderr)

    # Serialize as N-Triples and bulk-load with pyoxigraph
    print(f"[INFO] Serializing and bulk-loading with pyoxigraph...", file=sys.stderr)
    nt_data = g.serialize(format="ntriples")

    store.bulk_load(nt_data.encode("utf-8") if isinstance(nt_data, str) else nt_data, RdfFormat.N_TRIPLES)
    store.flush()

    print(f"[INFO] Loaded {len(g)} triples into persistent store.", file=sys.stderr)
    return len(g)


class SparqlHandler(BaseHTTPRequestHandler):
    """Minimal SPARQL 1.1 Protocol handler — query, update, and partial Graph Store."""

    store: Store = None  # Set by server factory
    data_dir: str = ""

    def log_message(self, fmt, *args):
        print(f"[{self.client_address[0]}] {fmt % args}", file=sys.stderr)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, Authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ("/", ""):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(YASGUI_HTML.encode("utf-8"))
            return

        if path == "/query":
            params = parse_qs(urlparse(self.path).query)
            query_str = params.get("query", [""])[0]
            self._handle_query(query_str)
            return

        self.send_response(404)
        self._cors()
        self.end_headers()
        self.wfile.write(b"Not found")

    def do_POST(self):
        path = urlparse(self.path).path

        if path in ("/query", "/sparql"):
            self._handle_post_query()
        elif path == "/update":
            self._handle_post_update()
        elif path == "/store":
            self._handle_post_store()
        else:
            self.send_response(404)
            self._cors()
            self.end_headers()
            self.wfile.write(b"Not found")

    def _handle_post_query(self):
        content_type = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")

        if "application/sparql-query" in content_type:
            query_str = body
        elif "application/x-www-form-urlencoded" in content_type:
            query_str = parse_qs(body).get("query", [""])[0]
        else:
            query_str = body
        self._handle_query(query_str)

    def _handle_post_update(self):
        content_type = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")

        if "application/sparql-update" in content_type:
            update_str = body
        elif "application/x-www-form-urlencoded" in content_type:
            update_str = parse_qs(body).get("update", [""])[0]
        else:
            update_str = body

        if not update_str.strip():
            self.send_response(400)
            self._cors()
            self.end_headers()
            self.wfile.write(b"Empty update")
            return

        try:
            self.store.update(update_str)
            self.store.flush()
            self.send_response(204)
            self._cors()
            self.end_headers()
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "text/plain")
            self._cors()
            self.end_headers()
            self.wfile.write(f"Update error: {e}".encode())

    def _handle_query(self, query_str: str):
        if not query_str.strip():
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(YASGUI_HTML.encode("utf-8"))
            return

        try:
            results = self.store.query(query_str)
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "text/plain")
            self._cors()
            self.end_headers()
            self.wfile.write(f"Query error: {e}".encode())
            return

        # ASK query returns bool
        if isinstance(results, bool):
            body = json.dumps({"head": {}, "boolean": results})
            self.send_response(200)
            self.send_header("Content-Type", "application/sparql-results+json")
            self._cors()
            self.end_headers()
            self.wfile.write(body.encode())
            return

        # SELECT query — try to get variables
        try:
            vars_list = list(results.variables)
            results_list = list(results)
        except AttributeError:
            # CONSTRUCT / DESCRIBE — iterable yields triples
            g = Graph()
            for triple in results:
                try:
                    g.add((triple.subject, triple.predicate, triple.object))
                except Exception:
                    g.add(triple)
            body = g.serialize(format="turtle")
            self.send_response(200)
            self.send_header("Content-Type", "text/turtle; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(body.encode() if isinstance(body, str) else body)
            return

        # SELECT — build JSON result
        out = {"head": {"vars": [str(v) for v in vars_list]}, "results": {"bindings": []}}
        for binding in results_list:
            row = {}
            for var in vars_list:
                try:
                    val = binding[var]
                    if val is not None:
                        row[str(var)] = _term_to_json(val)
                except (KeyError, IndexError):
                    pass
            out["results"]["bindings"].append(row)
        body = json.dumps(out, ensure_ascii=False)
        self.send_response(200)
        self.send_header("Content-Type", "application/sparql-results+json")
        self._cors()
        self.end_headers()
        self.wfile.write(body.encode())

    def _handle_post_store(self):
        content_type = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            self.store.bulk_load(body, RdfFormat.from_media_type(content_type) if content_type else None)
            self.store.flush()
            self.send_response(204)
            self._cors()
            self.end_headers()
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "text/plain")
            self._cors()
            self.end_headers()
            self.wfile.write(f"Store error: {e}".encode())


def _term_to_json(term) -> dict:
    """Convert a pyoxigraph NamedNode/Literal/BlankNode to SPARQL JSON result format."""
    from pyoxigraph import NamedNode, BlankNode, Literal
    if isinstance(term, NamedNode):
        return {"type": "uri", "value": term.value}
    elif isinstance(term, BlankNode):
        return {"type": "bnode", "value": term.value}
    elif isinstance(term, Literal):
        entry = {"type": "literal", "value": term.value}
        if term.language:
            entry["xml:lang"] = term.language
        if term.datatype:
            entry["datatype"] = term.datatype.value
        return entry
    return {"type": "literal", "value": str(term)}


def make_handler(store_obj, data_dir: str):
    """Factory to inject the Store into the handler."""
    class BoundHandler(SparqlHandler):
        pass
    BoundHandler.store = store_obj
    BoundHandler.data_dir = data_dir
    return BoundHandler


def serve(store: Store, data_dir: str, bind: str = "0.0.0.0", port: int = 7878):
    """Start the HTTP SPARQL endpoint."""
    handler = make_handler(store, data_dir)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f" SPARQL Endpoint (pyoxigraph)", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"", file=sys.stderr)
    print(f"  Web UI (YASGUI): http://localhost:{port}/", file=sys.stderr)
    print(f"  Query:    POST http://localhost:{port}/query", file=sys.stderr)
    print(f"  Update:   POST http://localhost:{port}/update", file=sys.stderr)
    print(f"  Store:    GET/POST http://localhost:{port}/store", file=sys.stderr)
    print(f"  Data dir: {data_dir}", file=sys.stderr)
    print(f"", file=sys.stderr)
    print(f"  curl -X POST http://localhost:{port}/query \\", file=sys.stderr)
    print(f"    -H 'Content-Type: application/sparql-query' \\", file=sys.stderr)
    print(f"    --data 'SELECT * WHERE {{ ?s ?p ?o }} LIMIT 10'", file=sys.stderr)
    print(f"", file=sys.stderr)
    print(f"  Add data:", file=sys.stderr)
    print(f"    curl -X POST http://localhost:{port}/store \\", file=sys.stderr)
    print(f"    -H 'Content-Type: text/turtle' -T file.ttl", file=sys.stderr)
    print(f"", file=sys.stderr)
    print(f"  Press Ctrl+C to stop.", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    server = HTTPServer((bind, port), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n[INFO] Endpoint stopped.", file=sys.stderr)
        store.flush()
        server.shutdown()


def main():
    parser = argparse.ArgumentParser(
        description="Deploy a SPARQL endpoint from RDF files using pyoxigraph"
    )
    parser.add_argument("repo_path", help="Path to the ontology repository")
    parser.add_argument("--port", type=int, default=7878, help="Port (default: 7878)")
    parser.add_argument("--bind", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--data-dir", default="oxigraph_data",
                        help="Persistent storage directory (default: ./oxigraph_data)")
    parser.add_argument("--no-serve", action="store_true",
                        help="Only merge and load, don't start endpoint")
    parser.add_argument("--serve-only", action="store_true",
                        help="Skip loading, only serve existing data")
    args = parser.parse_args()

    store = Store(args.data_dir)

    if not args.serve_only:
        try:
            count = merge_and_load(args.repo_path, store)
            store.flush()
        except Exception as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)

    if not args.no_serve:
        serve(store, args.data_dir, bind=args.bind, port=args.port)
    else:
        store.flush()
        print(f"[INFO] Data loaded and persisted at {args.data_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
