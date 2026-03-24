"""
CLI entry point for wows-replay-parser.

Usage:
    wowsreplay info replay.wowsreplay
    wowsreplay parse replay.wowsreplay --gamedata ./path/to/entity_defs
    wowsreplay events replay.wowsreplay --gamedata ./path/to/entity_defs
    wowsreplay state replay.wowsreplay --gamedata ./path/to/entity_defs --time 120.5
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

    cli()
