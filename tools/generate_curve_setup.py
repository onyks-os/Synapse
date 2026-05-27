"""
tools/generate_curve_setup.py

Generate CURVEZMQ setup for Synapse Mesh nodes.

This tool makes the strong security deploy path repeatable:
  - Generates N keypairs (one for each node).
  - Writes a peer_keys.txt file mapping node_id -> public_key.
  - Outputs per-node .env files containing its keys and the shared allowlist.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import zmq


def _z85_to_ascii(z85_bytes: bytes) -> str:
    return z85_bytes.decode("ascii")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def generate_keypair() -> tuple[str, str]:
    pub, sec = zmq.curve_keypair()
    return _z85_to_ascii(pub), _z85_to_ascii(sec)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Synapse Mesh CURVEZMQ setup."
    )
    parser.add_argument("--count", "-n", type=int, default=4, help="Number of nodes.")
    parser.add_argument("--out-dir", default=".curve-setup", help="Output directory.")
    parser.add_argument(
        "--node-id-template", default="node-{i:d}", help="NODE_ID template."
    )
    parser.add_argument(
        "--peer-keys-file", default="peer_keys.txt", help="Filename for shared keys."
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    peer_keys_path = out_dir / args.peer_keys_file
    node_env_dir = out_dir / "node-envs"

    nodes = []
    for i in range(1, args.count + 1):
        node_id = args.node_id_template.format(i=i)
        pub, sec = generate_keypair()
        nodes.append({"id": node_id, "pub": pub, "sec": sec})

    # Write peer_keys.txt
    peer_keys_content = "\n".join(f"{n['id']} {n['pub']}" for n in nodes)
    _write_text(peer_keys_path, peer_keys_content + "\n")

    # Write env files
    for n in nodes:
        env_path = node_env_dir / f"{n['id']}.env"
        env_content = "\n".join(
            [
                f"NODE_ID={n['id']}",
                f"SYNAPSE_CURVE_PUBLICKEY={n['pub']}",
                f"SYNAPSE_CURVE_SECRETKEY={n['sec']}",
                f"SYNAPSE_CURVE_PEER_KEYS_FILE=/config/{args.peer_keys_file}",
                "SYNAPSE_CURVE_ZAP_DOMAIN=*",
            ]
        )
        _write_text(env_path, env_content + "\n")

    print(f"Generated {args.count} mesh nodes in {out_dir}")


if __name__ == "__main__":
    main()
