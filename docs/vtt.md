# Virtual Tabletop

The **VTT** tab is a playable, original tabletop scene and a Visual Output
showcase. It uses familiar grid and token interactions without Foundry VTT
source code, assets, or proprietary implementation details.

## Start a game

1. Open **VTT** and describe the kind of setting, mystery, or adventure you
   want. Select **Build campaign map with AI**. The configured assistant route
   creates a map, campaign history, objective, points of interest, and initial
   NPCs. Invalid maps are rejected; start, exit, locations, and NPCs must be
   reachable on walkable terrain.
2. Switch between **Tabletop** for interactive movement and **Illustrated
   map** for a locally rendered, vector-style overview of the same AI-authored
   layout. The map's terrain, points, and actors come from the AI; AssiStuff
   draws the illustration and enforces the grid rules.
3. Read the terrain legend below the board. Click a highlighted tile to move
   the active player token. Row letters and column numbers identify positions.
4. Each turn gives the active player **4 movement points**. Open ground and
   road cost 1 point per tile; forest costs 2. Water and ridges cannot be
   crossed. The server-computed reachable tiles show the movement cost.
5. Select **End turn** to move to the next player and refill that player's
   movement points. **Locate player** selects the active token.
6. `?` markers are undiscovered locations. Move the active player onto one and
   select **Investigate location** to reveal its description.
7. Reach the orange **E** marker to complete the scene objective. Stop the LAN
   host before generating another map.
8. **Save scene snapshot** stores the visible scene as an HTML artifact.
   Snapshots are view-only; live map, turn, NPC, and location state is not
   restored when the app restarts.

The board shows row letters and numbered columns. Green dashed outlines mark
tiles reachable this turn. **Map & dice** includes a local 3d6 helper.

## Characters and hot-seat play

Use the **Character** tab to create a character, assign an optional origin,
archetype, level, experience, attributes, and skills, and optionally generate
an original backstory with AI. Select **Save character to this profile** to
store the sheet and backstory under the active profile's VTT directory.

The point-buy system is original and intentionally small:

- Body, Agility, Mind, and Presence each start at rank 2 and can range from 1
  to 5. Each rank above 2 costs 5 points, with a 40-point attribute budget.
- Skills have ranks 0–5, cost 2 points per rank, and share a 20-point budget.
  Enter skills one per line as `Skill name: rank`.
- A skill check uses a 3d6 roll-under target of
  `min(18, 8 + 2 × attribute rank + skill rank)`.

Use **Active player (shared-screen hot-seat)** to choose the current player.
Turn order cycles through the host and joined players. A scene supports at
most eight players, including the host.

These are not official GURPS rules or a complete GURPS implementation. Combat,
equipment, modifiers, critical results, and edition-specific rules are not
implemented. AI rule summaries are non-authoritative; verify rulings with the
game master and the table's chosen rules.

## LAN multiplayer

1. Keep the host computer on the same trusted local network as the players.
2. In **Multiplayer**, set the port if needed and select **Start LAN host**.
   Confirm the network exposure warning.
3. Share one displayed host URL and the join code with each player over a
   trusted channel. Players open the URL in a browser and enter their player
   name, character name, and attributes to join.
4. The browser board shows the illustrated AI-built map, current players,
   NPCs, locations, and turns. The active player can move to server-designated
   reachable tiles, investigate, roll 3d6, speak with an NPC, and ask the
   Storyteller GM. **Leave game** removes that player's token and session.
5. Select **Stop LAN host** when the session is over.

The host runs all assistant requests; browser clients do not need their own
model installation. The transport is plain, unencrypted HTTP, and anyone with
the join code can participate. Use only a trusted LAN; do not expose the port
to the public internet. Regenerating a map requires stopping the host first.
Joined players and in-memory scene state are not persisted as a resumable
campaign.

## Active AI game master and campaign history

The map generator creates campaign premise, world history, timeline, current
conflict, initial NPCs, and an objective. Use the **History** tab to generate
or expand the campaign history, generate an AI recap from recent session
events, and review the full in-session chronicle. Map generation also creates
chronicle entries for later play. Character backstories can be generated from
the **Character** tab and saved with the character sheet.

In **Storyteller GM**, declare what the active character attempts. The GM uses
the current campaign history, map, party, discovered locations, NPCs, last
roll, and recent chronicle. It may call for a skill check; AssiStuff calculates
the target and rolls 3d6 locally, then asks the GM to adjudicate that exact
result. The GM can propose location reveals, NPC additions/movement, and
objective updates. These changes are schema- and state-validated by the host
before they are applied. All movement and dice remain governed by the local
game engine; the GM cannot directly edit arbitrary state.

Use the **NPC** tab to place an NPC on a walkable tile and start a separate
conversation. NPC, GM, map, history, backstory, and rules-help requests use the
configured assistant route. Prompts may be sent to a remote provider if remote
routing is configured; avoid including private campaign or character details
unless that provider is trusted. The HTML artifact viewer has no host bridge
and cannot call models, memory, or dice services.

Campaign history and the session chronicle are in-memory and appear in saved
HTML snapshots, but the live scene is not restored when the app restarts.

## Configuration

```yaml
vtt:
  ruleset: gurps_3d6
  map_width: 16
  map_height: 10
```

Width is limited to 8–32 tiles and height to 8–24. VTT acceptance testing
remains user-owned.
