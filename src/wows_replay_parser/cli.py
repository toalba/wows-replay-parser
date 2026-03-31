"""
CLI entry point for wows-replay-parser.

Usage:
    wowsreplay info replay.wowsreplay
    wowsreplay parse replay.wowsreplay --gamedata ./path/to/entity_defs
    wowsreplay events replay.wowsreplay --gamedata ./path/to/entity_defs
    wowsreplay state replay.wowsreplay --gamedata ./path/to/entity_defs --time 120.5
    wowsreplay export replay.wowsreplay --gamedata ./path/to/entity_defs -o replay.json
"""

from __future__ import annotations


def main() -> None:
    """CLI entrypoint — requires click + rich (install with [cli] extra)."""
    try:
        import click
    except ImportError:
        print("CLI requires extra dependencies: pip install -e '.[cli]'")
        raise SystemExit(1) from None

    @click.group()
    def cli() -> None:
        """WoWs Replay Parser — parse .wowsreplay files."""

    @cli.command()
    @click.argument("replay_path", type=click.Path(exists=True))
    def info(replay_path: str) -> None:
        """Show replay metadata (no gamedata needed)."""
        from pathlib import Path

        from rich.console import Console
        from rich.pretty import pprint

        from wows_replay_parser.replay.reader import ReplayReader

        console = Console()
        replay = ReplayReader().read(Path(replay_path))

        console.print(f"[bold]Game Version:[/] {replay.game_version}")
        console.print(f"[bold]Map:[/] {replay.map_name}")
        console.print(f"[bold]Player:[/] {replay.player_name}")
        console.print(f"[bold]Complete:[/] {replay.is_complete}")
        console.print(f"[bold]Packet data:[/] {len(replay.packet_data)} bytes")
        console.print()
        console.print("[bold]Players:[/]")
        pprint(replay.players)

    @cli.command()
    @click.argument("replay_path", type=click.Path(exists=True))
    @click.option(
        "--gamedata", required=True, type=click.Path(exists=True),
        help="Path to wows-gamedata entity_defs directory",
    )
    @click.option("--limit", default=50, help="Max packets to show")
    def parse(replay_path: str, gamedata: str, limit: int) -> None:
        """Parse replay packets using gamedata."""
        from pathlib import Path

        from rich.console import Console
        from rich.table import Table

        from wows_replay_parser.api import parse_replay

        console = Console()
        result = parse_replay(Path(replay_path), Path(gamedata))

        table = Table(
            title=(
                f"Packets ({len(result.packets)} total, "
                f"showing {min(limit, len(result.packets))})"
            ),
        )
        table.add_column("Time", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Entity", style="yellow")
        table.add_column("Detail")

        for pkt in result.packets[:limit]:
            detail = ""
            if pkt.method_name:
                detail = f"{pkt.entity_type}.{pkt.method_name}"
            elif pkt.property_name:
                detail = f"{pkt.entity_type}.{pkt.property_name}"
            elif pkt.position:
                detail = (
                    f"({pkt.position[0]:.1f}, "
                    f"{pkt.position[1]:.1f}, "
                    f"{pkt.position[2]:.1f})"
                )

            table.add_row(
                f"{pkt.timestamp:.2f}",
                pkt.type.name,
                str(pkt.entity_id),
                detail,
            )

        console.print(table)

    @cli.command()
    @click.argument("replay_path", type=click.Path(exists=True))
    @click.option(
        "--gamedata", required=True, type=click.Path(exists=True),
    )
    @click.option(
        "--type", "event_type", default=None,
        help="Filter by event type name",
    )
    @click.option("--limit", default=50, help="Max events to show")
    def events(
        replay_path: str,
        gamedata: str,
        event_type: str | None,
        limit: int,
    ) -> None:
        """Extract typed game events from a replay."""
        from pathlib import Path

        from rich.console import Console
        from rich.pretty import pprint

        from wows_replay_parser.api import parse_replay

        console = Console()
        result = parse_replay(Path(replay_path), Path(gamedata))
        all_events = result.events

        if event_type:
            all_events = [
                e for e in all_events
                if type(e).__name__ == event_type
            ]

        console.print(f"[bold]{len(all_events)} events[/]")
        for event in all_events[:limit]:
            pprint(event)

    @cli.command()
    @click.argument("replay_path", type=click.Path(exists=True))
    @click.option(
        "--gamedata", required=True, type=click.Path(exists=True),
    )
    @click.option(
        "--time", "timestamp", required=True, type=float,
        help="Game time in seconds to query state at",
    )
    def state(
        replay_path: str, gamedata: str, timestamp: float,
    ) -> None:
        """Show game state at a specific timestamp."""
        from pathlib import Path

        from rich.console import Console
        from rich.pretty import pprint

        from wows_replay_parser.api import parse_replay

        console = Console()
        result = parse_replay(Path(replay_path), Path(gamedata))
        game_state = result.state_at(timestamp)

        console.print(f"[bold]Game State at t={timestamp:.1f}s[/]")
        console.print(f"[bold]Ships:[/] {len(game_state.ships)}")
        console.print()

        for eid, ship in game_state.ships.items():
            alive = "[green]ALIVE[/]" if ship.is_alive else "[red]DEAD[/]"
            console.print(
                f"  Entity {eid}: {alive} "
                f"HP={ship.health:.0f}/{ship.max_health:.0f} "
                f"Team={ship.team_id}"
            )

        console.print()
        console.print("[bold]Battle:[/]")
        pprint(game_state.battle)

    @cli.command()
    @click.argument("replay_path", type=click.Path(exists=True))
    @click.option(
        "--gamedata", required=True, type=click.Path(exists=True),
        help="Path to wows-gamedata entity_defs directory",
    )
    @click.option(
        "-o", "--output", default=None, type=click.Path(),
        help="Output JSON file (default: stdout)",
    )
    @click.option(
        "--no-positions", is_flag=True,
        help="Exclude PositionEvent (reduces output ~5x)",
    )
    @click.option(
        "--no-properties", is_flag=True,
        help="Exclude PropertyUpdateEvent",
    )
    @click.option(
        "--no-raw", is_flag=True,
        help="Exclude RawEvent (unmatched methods)",
    )
    @click.option("--pretty", is_flag=True, help="Pretty-print JSON")
    @click.option(
        "--snapshot-interval", default=5.0, type=float,
        help="State snapshot interval in seconds (0 to disable, default: 5)",
    )
    def export(
        replay_path: str,
        gamedata: str,
        output: str | None,
        no_positions: bool,
        no_properties: bool,
        no_raw: bool,
        pretty: bool,
        snapshot_interval: float,
    ) -> None:
        """Export replay to structured JSON."""
        import dataclasses
        import json
        import sys
        from pathlib import Path

        from wows_replay_parser.api import parse_replay

        result = parse_replay(Path(replay_path), Path(gamedata))

        def _make_serializable(obj: object) -> object:
            """Recursively convert an object to JSON-safe types."""
            if obj is None or isinstance(obj, (bool, int, float, str)):
                return obj
            if isinstance(obj, bytes):
                if len(obj) == 0:
                    return None
                return f"<{len(obj)} bytes>"
            if isinstance(obj, dict):
                return {
                    (str(k) if isinstance(k, tuple) else k): _make_serializable(v)
                    for k, v in obj.items()
                    if not (isinstance(k, str) and k.startswith("_"))
                }
            if isinstance(obj, (list, tuple)):
                return [_make_serializable(v) for v in obj]
            if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                return {
                    f.name: _make_serializable(getattr(obj, f.name))
                    for f in dataclasses.fields(obj)
                }
            # _AttrObject or other pickle-reconstructed objects
            if hasattr(obj, "__dict__"):
                d = {
                    k: _make_serializable(v)
                    for k, v in obj.__dict__.items()
                    if not k.startswith("_")
                }
                d["__class__"] = type(obj).__name__
                return d
            # Container (construct library)
            if hasattr(obj, "items"):
                return {
                    str(k): _make_serializable(v) for k, v in obj.items()
                    if not str(k).startswith("_")
                }
            return str(obj)

        # Filter events
        skip_types: set[str] = set()
        if no_positions:
            skip_types.add("PositionEvent")
        if no_properties:
            skip_types.add("PropertyUpdateEvent")
        if no_raw:
            skip_types.add("RawEvent")

        events_out = []
        for ev in result.events:
            etype = type(ev).__name__
            if etype in skip_types:
                continue
            d = _make_serializable(ev)
            if isinstance(d, dict):
                d["event_type"] = etype
                d.pop("raw_data", None)
            events_out.append(d)

        # Players
        players_out = _make_serializable(result.players)

        # State snapshots
        snapshots_out: list[object] = []
        if snapshot_interval > 0 and result.duration > 0:
            import math
            timestamps = [
                i * snapshot_interval
                for i in range(int(math.ceil(result.duration / snapshot_interval)) + 1)
            ]
            for game_state in result.iter_states(timestamps):
                snap: dict[str, object] = {
                    "timestamp": round(game_state.timestamp, 2),
                    "ships": {},
                    "battle": {
                        "team_scores": game_state.battle.team_scores,
                        "time_left": game_state.battle.time_left,
                    },
                }
                for eid, ship in game_state.ships.items():
                    snap["ships"][eid] = {
                        "health": round(ship.health, 1),
                        "max_health": round(ship.max_health, 1),
                        "is_alive": ship.is_alive,
                        "team_id": ship.team_id,
                        "position": (
                            round(ship.position[0], 2),
                            round(ship.position[1], 2),
                            round(ship.position[2], 2),
                        ) if ship.position != (0.0, 0.0, 0.0) else None,
                        "yaw": round(ship.yaw, 4) if ship.yaw else None,
                        "speed": round(ship.speed, 1) if ship.speed else None,
                        "is_detected": ship.is_detected,
                        "burning": ship.burning_flags != 0,
                    }
                snapshots_out.append(snap)

        # Build output
        doc: dict[str, object] = {
            "meta": {
                "map": result.map_name,
                "version": result.game_version,
                "duration": round(result.duration, 2),
                "player_count": len(result.players),
                "snapshot_interval": snapshot_interval if snapshot_interval > 0 else None,
            },
            "players": players_out,
            "state_snapshots": snapshots_out,
            "events": events_out,
        }

        indent = 2 if pretty else None
        json_str = json.dumps(doc, indent=indent, ensure_ascii=False)

        if output:
            Path(output).write_text(json_str, encoding="utf-8")
            click.echo(
                f"Exported {len(events_out)} events, "
                f"{len(snapshots_out)} snapshots, "
                f"{len(result.players)} players -> {output}"
            )
        else:
            sys.stdout.write(json_str)
            sys.stdout.write("\n")

    cli()
