# Virtual Tabletop

The **VTT** tab is a playable, original tabletop scene and a Visual Output
showcase. It uses familiar grid and token interactions without Foundry VTT
source code, assets, or proprietary implementation details.

## Start a game

1. Open **VTT**. The map is generated locally from a repeatable seed.
2. Read the terrain legend below the board. Click a highlighted tile to move
   the active player token. Row letters and column numbers identify positions.
3. Each turn gives the active player **4 movement points**. Open ground and
   road cost 1 point per tile; forest costs 2. Water and ridges cannot be
   crossed. The server-computed reachable tiles show the movement cost.
4. Select **End turn** to move to the next player and refill that player's
   movement points. **Locate player** selects the active token.
5. `?` markers are undiscovered locations. Move the active player onto one and
   select **Investigate location** to reveal its description.
6. Reach the orange **E** marker to complete the scene objective. Stop the LAN
   host before generating another map.
7. **Save scene snapshot** stores the visible scene as an HTML artifact.
   Snapshots are view-only; live map, turn, NPC, and location state is not
   restored when the app restarts.

The board shows row letters and numbered columns. Green dashed outlines mark
tiles reachable this turn. **Map & dice** includes a local 3d6 helper.

## Characters and hot-seat play

Use the **Character** tab to create a character, assign an optional origin,
archetype, level, experience, attributes, and skills, then select **Save
character to this profile**. Character sheets are stored under the active
profile's VTT directory.

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
4. The browser board shows current players, NPCs, locations, and turns. The
   active player can move to server-designated reachable tiles, investigate,
   roll 3d6, speak with an NPC, and ask the Storyteller GM. **Leave game**
   removes that player's token and session.
5. Select **Stop LAN host** when the session is over.

The host runs all assistant requests; browser clients do not need their own
model installation. The transport is plain, unencrypted HTTP, and anyone with
the join code can participate. Use only a trusted LAN; do not expose the port
to the public internet. Regenerating a map requires stopping the host first.
Joined players and in-memory scene state are not persisted as a resumable
campaign.

## NPCs, Storyteller, and privacy

Use the **NPC** tab to place an original NPC on a walkable map tile and ask
them a question. Use **Storyteller GM** to request an original scene
continuation and suggested choices based on the current party and map. The
client and GUI validate structured NPC/Storyteller JSON before displaying it.
AI narration does not directly mutate game state.

NPC, Storyteller, and rules-help requests use the configured assistant
dispatcher. They may go to a remote provider if the assistant is configured
that way; avoid sending private campaign material unless the provider is
trusted. The HTML artifact viewer has no host bridge and cannot call models,
memory, or dice services.

## Configuration

```yaml
vtt:
  ruleset: gurps_3d6
  map_width: 16
  map_height: 10
```

Width is limited to 8–32 tiles and height to 8–24. VTT acceptance testing
remains user-owned.
