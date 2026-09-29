"""``python -m clinical_engine.review_workbench`` — serve the workbench, loopback only.

The owner token is printed exactly once, on the operator's own terminal, and
only its SHA-256 is written to the reviewer registry. It is used to mint the
per-reviewer session tokens that the API then requires on the
``X-Review-Token`` header.
"""

from __future__ import annotations

import argparse

from .api import run_server


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m clinical_engine.review_workbench")
    parser.add_argument("--database", default="review_workbench.sqlite")
    parser.add_argument("--registry", default="reviewer_registry.sqlite")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Loopback only. Any other value is refused.")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--owner-token", default=None,
                        help="Reuse a previously issued owner token. Only its "
                             "SHA-256 is stored; the raw value cannot be recovered.")
    args = parser.parse_args()
    run_server(args.database, args.registry, host=args.host, port=args.port,
               owner_token=args.owner_token)


if __name__ == "__main__":
    main()
