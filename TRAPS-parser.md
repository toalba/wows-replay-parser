# Parser Traps (aus Landaire's wows-toolkit Analyse)

Fallstricke die den Replay-Parser betreffen. Aus der Analyse von `wows-toolkit/crates/wows-replays/`.

---

## Trap 1: Packet Type Mapping — 0x07 vs 0x08

Korrektes Mapping (aus Landaire bestätigt):
```
0x00 = BasePlayerCreate
0x01 = CellPlayerCreate
0x02 = EntityControl
0x03 = EntityEnter
0x04 = EntityLeave
0x05 = EntityCreate
0x07 = EntityProperty
0x08 = EntityMethod
0x0A = Position
0x0E = ServerTick
0x0F = ServerTimestamp
0x16 = Version
0x1D = PlayerNetStats (fps/ping/lag packed in u32)
0x20 = OwnShip
0x22 = BattleResults
0x23 = NestedPropertyUpdate
0x25 = Camera
0x27 = CameraMode (NOT Map!)
0x28 = Map
0x2A = NonVolatilePosition (SmokeScreen, weather)
0x2C = PlayerOrientation
0x33 = ShotTracking (new since ~Feb 2026)
```

Python Reference-Parsers haben teilweise 0x07 und 0x08 vertauscht. **Bounty-kritisch.**

---

## Trap 2: Packet 0x22 ist BattleResults, NICHT NestedProperty

Im Python-Kommentar von Monstrofil steht `0x22: NestedProperty`, aber Landaire parsed 0x22 als `BattleResults` und 0x23 als `NestedPropertyUpdate`. Bekannter Fehler im originalen Mapping.

---

## Trap 3: Packet Header ist 12 Bytes

```
4 bytes: packet_size (payload length, excludes header)
4 bytes: packet_type
4 bytes: clock (f32, game time)
N bytes: payload (packet_size bytes)
```

Clock ist ein f32 im Header — JEDES Paket hat einen Zeitstempel. Falsches Header-Parsing → alle Timestamps driften. **Bounty-kritisch.**

---

## Trap 4: CellPlayerCreate MUSS nach BasePlayerCreate kommen

Landaire: `panic!("Cell player, entity id {}, was created before base player!")`. Reihenfolge ist: erst 0x00 (BasePlayerCreate), dann 0x01 (CellPlayerCreate). Entity-State aufbauen bevor beide Pakete da sind → fehlende Properties. **Bounty-kritisch.**

---

## Trap 5: Zwei getrennte Positionsquellen

Schiffe haben **zwei verschiedene Positionsquellen** die parallel existieren:

1. **Position-Pakete (0x0A)** — World-Koordinaten in Space-Units, mit direction/rotation
2. **`updateMinimapVisionInfo` (EntityMethod)** — Normalisierte 11-bit Koordinaten mit Sichtbarkeit

Der Parser muss BEIDE liefern. Position-Pakete geben präzise World-Coords, MinimapVisionInfo gibt Sichtbarkeits-Status und ist authoritative für die Minimap-Darstellung.

Ohne MinimapVisionInfo fehlt dem Renderer: Sichtbarkeits-Status, Heading, ob ein Schiff detected ist. **Bounty-kritisch.**

---

## Trap 6: updateMinimapVisionInfo Bitfield Layout

32-bit `packedData`:
```
Bit  0-10:  x (11 bits)
Bit 11-21:  y (11 bits)
Bit 22-29:  heading (8 bits)
Bit 30:     unknown
Bit 31:     is_disappearing
```

Konvertierungen:
```python
# Heading
heading_degrees = raw_heading / 256.0 * 360.0 - 180.0

# Position (Landaire speichert als Zwischenwert)
stored_x = raw_x / 512.0 - 1.5
stored_y = raw_y / 512.0 - 1.5

# Rückrechnung zu World-Koordinaten für Minimap-Mapping:
world_x = (stored_x + 1.5) * 512.0 / 2047.0 * 5000.0 - 2500.0
world_z = (stored_y + 1.5) * 512.0 / 2047.0 * 5000.0 - 2500.0
```

**Sentinel-Check:** `raw_x == 0 && raw_y == 0` ist ein Sentinel (keine gültige Position), NICHT Position (-2500, -2500). Ohne diese Prüfung landen Schiffe fälschlich in der Ecke.

**is_disappearing:** `true` mit gültiger Position = Schiff verschwindet (wurde undetected). Position ist gültig zum Zeitpunkt des Verschwindens. **Bounty-kritisch.**

---

## Trap 7: Artillery Shots — Flugzeit-Daten

`receiveArtilleryShots` liefert pro Shell:
- `pos` (origin)
- `tarPos` (target)
- `speed` (m/s)
- `pitch`
- `shotID`
- `serverTimeLeft`
- `hitDistance`
- `shooterHeight`
- `gunBarrelID`

Die Flugzeit wird berechnet als:
```python
distance = dist(origin, target)
flight_duration = distance / speed
```

Ohne speed/time-Daten können wir keine animierten Tracer zeichnen — nur statische Linien. **Bounty-kritisch.**

---

## Trap 8: Torpedos haben Richtungsvektor, KEINE Zielposition

Im Gegensatz zu Shells haben Torpedos:
- `pos` (origin)
- `dir` (direction vector, Magnitude = Geschwindigkeit in m/s)
- `armed` (bool)
- `shotID`
- `maneuverDump` (optional, für S-Turn Torps)
- `acousticDump` (optional, für Homing Torps)

Es gibt KEIN `tarPos`. Aktuelle Position:
```python
position = origin + direction * elapsed_time
```

S-Turn Torps (`maneuverDump` != None) brauchen Arc-Integration:
```python
# Während der Kurve (elapsed < turn_duration):
# Analytisches Arc-Integral über sin/cos
# Nach der Kurve: gerade Linie ab Endpunkt der Kurve
```

Alle Torps als gerade Linien = alternative/homing Torps gehen daneben. **Bounty-kritisch.**

---

## Trap 9: receiveShotKills enthält ALLE Hits, nicht nur Kills

`receiveShotKills` ist falsch benannt. Es enthält alle Projektil-Treffer:
- `ownerID` — wer hat geschossen
- `hitType` — Penetration, Overpen, Bounce, Shatter, etc. (aus ShipsConstants)
- `shotID` — welches Projektil
- `pos` — Trefferpunkt
- `terminalBallisticsInfo` (optional) — Position, Velocity, DetonatorActivated, MaterialAngle

Diese Daten sind die Basis für Ribbon-Derivation. Ohne `hitType` keine Ribbons. **P2 aber wichtig.**

---

## Trap 10: NonVolatilePosition (Packet 0x2A)

Smoke-Screens und Weather-Zones nutzen einen eigenen Positions-Pakettyp:
```
0x2A = NonVolatilePosition
Format: entity_id(u32) + space_id(u32) + position(Vec3) + rotation(Rot3)
```

Gleiche Struktur wie Position-Paket (0x0A) aber OHNE direction und is_on_ground. Ohne dieses Paket → keine Smoke-Positionen auf der Minimap.

---

## Trap 11: Game Constants müssen zur Replay-Version passen

Landaire merged `CONSUMABLE_IDS` und `BATTLE_STAGES` aus einer JSON-Datei versioniert nach Build-Nummer. Wenn Constants nicht zur Replay-Version passen → Consumables und BattleStages falsch aufgelöst.

Unser `extracted_constants.json` aus dem gamedata Repo deckt das ab, aber muss bei jedem Patch aktualisiert werden (passiert automatisch durch die Pipeline).

---

## Trap 12: BattleStage-Enum ist invertiert

```
BattleStage::Battle  (raw value 1) = PRE-BATTLE COUNTDOWN
BattleStage::Waiting (raw value 0) = BATTLE ACTIVE
```

Kontra-intuitiv. "Battle" = Countdown, "Waiting" = Match läuft. **Bounty-kritisch.**

---

## Trap 13: Dead Ship Positions explizit cachen

Bei Kill-Events muss die AKTUELLE Position des Schiffs gecached werden:
- World-Position aus letztem Position-Paket
- Minimap-Position als Fallback

Landaire speichert explizit `DeadShip { clock, position, minimap_position }`. Ohne Cache verschwinden tote Schiffe einfach. **Bounty-kritisch.**

---

## Zusammenfassung Parser-Traps

| # | Trap | Impact | Bounty-kritisch? |
|---|------|--------|-------------------|
| 1 | 0x07/0x08 Mapping | Properties/Methods vertauscht | JA |
| 2 | 0x22 = BattleResults | Falsch als NestedProperty | MITTEL |
| 3 | Header 12 Bytes | Timestamps driften | JA |
| 4 | Cell before Base | Parser crasht | JA |
| 5 | Dual Position Sources | Sichtbarkeit fehlt | JA |
| 6 | Minimap Bitfield 11+11+8+1+1 | Positions-Parsing kaputt | JA |
| 7 | Shell Flugzeit-Daten | Keine animierten Tracer | JA |
| 8 | Torpedo dir != tarPos | Torps falsch positioniert | JA |
| 9 | ShotKills = alle Hits | Keine Ribbons | P2 |
| 10 | NonVolatile Pos 0x2A | Kein Smoke | MITTEL |
| 11 | Constants Version-Match | Enums falsch | MITTEL |
| 12 | BattleStage invertiert | Timer kaputt | JA |
| 13 | Dead Ship Position Cache | Tote verschwinden | JA |
