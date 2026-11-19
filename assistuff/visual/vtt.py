"""VTT scene data, deterministic map generation, dice, and HTML rendering."""

from __future__ import annotations

import heapq
import json
import os
import random
import re
import secrets
import tempfile
from dataclasses import dataclass, field
from hashlib import sha256
from html import escape
from pathlib import Path
from typing import Annotated, ClassVar, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

Terrain = Literal["field", "forest", "water", "ridge", "road"]
Position = tuple[int, int]

_TERRAIN_MARKS: dict[Terrain, str] = {
    "field": "F",
    "forest": "T",
    "water": "W",
    "ridge": "R",
    "road": "·",
}
_MOVE_COST: dict[Terrain, int] = {"field": 1, "forest": 2, "road": 1}
_POINT_SPECS = (
    ("camp", "Wayfarer's camp", "camp", "A sheltered place beside the old trail."),
    ("ruins", "Broken watchtower", "ruins", "A weathered lookout with a view of the road."),
    ("shrine", "Roadside shrine", "shrine", "A small marker left by earlier travelers."),
)


@dataclass(frozen=True)
class MapPoint:
    point_id: str
    name: str
    kind: Literal["camp", "ruins", "shrine"]
    description: str
    position: Position


@dataclass(frozen=True)
class ProceduralMap:
    seed: str
    width: int
    height: int
    tiles: tuple[tuple[Terrain, ...], ...]
    start: Position
    exit: Position
    points: tuple[MapPoint, ...] = ()


class NpcReply(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    dialogue: str = Field(min_length=1, max_length=1200)
    mood: str = Field(default="neutral", min_length=1, max_length=40)
    suggested_actions: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(
        default_factory=list, max_length=4
    )


class VttCharacter(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    character_id: str = Field(default_factory=lambda: secrets.token_urlsafe(9), max_length=64)
    name: str = Field(min_length=1, max_length=64)
    player_name: str = Field(min_length=1, max_length=64)
    origin: str = Field(default="Wanderer", min_length=1, max_length=80)
    archetype: str = Field(default="Adventurer", min_length=1, max_length=80)
    level: int = Field(default=1, ge=1, le=20)
    experience: int = Field(default=0, ge=0, le=1_000_000)
    body: int = Field(default=2, ge=1, le=5)
    agility: int = Field(default=2, ge=1, le=5)
    mind: int = Field(default=2, ge=1, le=5)
    presence: int = Field(default=2, ge=1, le=5)
    skills: dict[str, int] = Field(default_factory=dict, max_length=8)

    ATTRIBUTE_POINT_BUDGET: ClassVar[int] = 40
    SKILL_POINT_BUDGET: ClassVar[int] = 20

    @field_validator("character_id")
    @classmethod
    def _valid_character_id(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
            raise ValueError("character ID contains unsupported characters")
        return value

    @field_validator("skills")
    @classmethod
    def _normalize_skills(cls, value: dict[str, int]) -> dict[str, int]:
        normalized: dict[str, int] = {}
        names: set[str] = set()
        for name, rank in value.items():
            label = name.strip()
            key = label.casefold()
            if not label or len(label) > 40 or key in names:
                raise ValueError("skill names must be unique and contain 1-40 characters")
            names.add(key)
            normalized[label] = rank
        return normalized

    @model_validator(mode="after")
    def _validate_point_budgets(self) -> VttCharacter:
        attribute_spend = sum(
            max(0, getattr(self, attribute) - 2) * 5
            for attribute in ("body", "agility", "mind", "presence")
        )
        if attribute_spend > self.ATTRIBUTE_POINT_BUDGET:
            raise ValueError(
                f"attributes spend {attribute_spend} points; "
                f"budget is {self.ATTRIBUTE_POINT_BUDGET}"
            )
        if any(not name.strip() or len(name) > 40 for name in self.skills):
            raise ValueError("skill names must contain 1-40 characters")
        if any(not 0 <= rank <= 5 for rank in self.skills.values()):
            raise ValueError("skill ranks must be between 0 and 5")
        skill_spend = sum(self.skills.values()) * 2
        if skill_spend > self.SKILL_POINT_BUDGET:
            raise ValueError(
                f"skills spend {skill_spend} points; budget is {self.SKILL_POINT_BUDGET}"
            )
        return self

    @property
    def attribute_points_spent(self) -> int:
        return sum(
            max(0, getattr(self, attribute) - 2) * 5
            for attribute in ("body", "agility", "mind", "presence")
        )

    @property
    def skill_points_spent(self) -> int:
        return sum(self.skills.values()) * 2

    def skill_target(self, skill: str, attribute: str) -> int:
        if attribute not in {"body", "agility", "mind", "presence"}:
            raise ValueError(f"unknown character attribute: {attribute}")
        return min(18, 8 + getattr(self, attribute) * 2 + self.skills.get(skill, 0))


class VttCharacterStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[VttCharacter]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("character store must contain a list")
            return [VttCharacter.model_validate(item) for item in data]
        except (OSError, json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise ValueError(f"could not load VTT characters: {exc}") from exc

    def save(self, character: VttCharacter) -> None:
        characters = self.load()
        for index, current in enumerate(characters):
            if current.character_id == character.character_id:
                characters[index] = character
                break
        else:
            characters.append(character)

        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        document = json.dumps(
            [item.model_dump(mode="json") for item in characters],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(prefix=".characters-", dir=self.path.parent)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(document)
            os.replace(temporary, self.path)
        except OSError:
            Path(temporary).unlink(missing_ok=True)
            raise


@dataclass
class VttPlayer:
    player_id: str
    player_name: str
    character: VttCharacter | None
    position: Position
    moves_remaining: int = 4


@dataclass(frozen=True)
class NpcActor:
    name: str
    role: str
    position: Position
    personality: str = ""
    npc_id: str = field(default_factory=lambda: secrets.token_urlsafe(9))


class StorytellerReply(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    narration: str = Field(min_length=1, max_length=1800)
    choices: list[Annotated[str, Field(min_length=1, max_length=180)]] = Field(
        default_factory=list,
        max_length=4,
    )


@dataclass(frozen=True)
class StorytellerExchange:
    player_name: str
    prompt: str
    reply: StorytellerReply


@dataclass(frozen=True)
class NpcExchange:
    name: str
    role: str
    reply: NpcReply
    actor_id: str | None = None


@dataclass(frozen=True)
class DiceRoll:
    target: int
    dice: tuple[int, int, int]
    total: int

    @property
    def success(self) -> bool:
        return self.total <= self.target

    @property
    def margin(self) -> int:
        return self.target - self.total if self.success else self.total - self.target


@dataclass
class VttScene:
    map: ProceduralMap
    npc_exchanges: list[NpcExchange] = field(default_factory=list)
    npcs: list[NpcActor] = field(default_factory=list)
    storyteller_exchanges: list[StorytellerExchange] = field(default_factory=list)
    rules_help: str = ""
    last_roll: DiceRoll | None = None
    game: VttGame = field(init=False)

    def __post_init__(self) -> None:
        self.game = VttGame(self.map)


@dataclass
class VttGame:
    map: ProceduralMap
    turn: int = 1
    moves_per_turn: int = 4
    discovered_points: set[str] = field(default_factory=set)
    completed: bool = False
    players: list[VttPlayer] = field(default_factory=list)
    active_player_id: str = "host"

    def __post_init__(self) -> None:
        if not self.players:
            self.players.append(
                VttPlayer(
                    player_id="host",
                    player_name="Host",
                    character=None,
                    position=self.map.start,
                    moves_remaining=self.moves_per_turn,
                )
            )
        if self.active_player_id not in {player.player_id for player in self.players}:
            self.active_player_id = self.players[0].player_id

    @property
    def active_player(self) -> VttPlayer:
        return self._player(self.active_player_id)

    @property
    def player_position(self) -> Position:
        return self.active_player.position

    @player_position.setter
    def player_position(self, value: Position) -> None:
        self.active_player.position = value

    @property
    def moves_remaining(self) -> int:
        return self.active_player.moves_remaining

    @moves_remaining.setter
    def moves_remaining(self, value: int) -> None:
        self.active_player.moves_remaining = value

    @property
    def player_label(self) -> str:
        x, y = self.active_player.position
        return f"{chr(ord('A') + y)}{x + 1}"

    def add_player(self, player_id: str, character: VttCharacter) -> VttPlayer:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", player_id):
            raise ValueError("player ID contains unsupported characters")
        if any(player.player_id == player_id for player in self.players):
            raise ValueError("player is already in this scene")
        if len(self.players) >= 8:
            raise ValueError("a VTT scene supports at most eight players")
        occupied = {player.position for player in self.players}
        candidates = sorted(
            (
                (x, y)
                for y, row in enumerate(self.map.tiles)
                for x, terrain in enumerate(row)
                if terrain in _MOVE_COST and (x, y) not in occupied
                and (x, y) != self.map.exit
                and all(point.position != (x, y) for point in self.map.points)
            ),
            key=lambda position: (
                abs(position[0] - self.map.start[0])
                + abs(position[1] - self.map.start[1]),
                position[1],
                position[0],
            ),
        )
        if not candidates:
            raise ValueError("no open starting tile is available")
        player = VttPlayer(
            player_id=player_id,
            player_name=character.player_name,
            character=character,
            position=candidates[0],
            moves_remaining=self.moves_per_turn,
        )
        self.players.append(player)
        return player

    def set_character(self, player_id: str, character: VttCharacter) -> VttPlayer:
        player = self._player(player_id)
        player.player_name = character.player_name
        player.character = character
        return player

    def remove_player(self, player_id: str) -> None:
        if player_id == "host":
            raise ValueError("the host player cannot be removed")
        player = self._player(player_id)
        self.players.remove(player)
        if self.active_player_id == player_id:
            self.active_player_id = next(
                (item.player_id for item in self.players if item.player_id == "host"),
                self.players[0].player_id,
            )

    def select_player(self, player_id: str) -> None:
        self._player(player_id)
        self.active_player_id = player_id

    def reachable_costs(self, player_id: str | None = None) -> dict[Position, int]:
        if self.completed:
            return {}
        player = self._player(player_id or self.active_player_id)
        routes = self._routes(player.position, player.moves_remaining)
        routes.pop(player.position, None)
        return routes

    def route_to(
        self,
        destination: Position,
        player_id: str | None = None,
    ) -> tuple[tuple[Position, ...], int]:
        player = self._player(player_id or self.active_player_id)
        if not self._in_bounds(destination):
            raise ValueError("destination is outside the map")
        if destination == player.position:
            raise ValueError("player is already at that location")
        if self.map.tiles[destination[1]][destination[0]] not in _MOVE_COST:
            raise ValueError("that terrain cannot be crossed")
        costs = self._routes(player.position)
        if destination not in costs:
            raise ValueError("no walkable route reaches that tile")
        return self._build_path(destination, player.position), costs[destination]

    def move_to(self, destination: Position, player_id: str | None = None) -> int:
        if self.completed:
            raise ValueError("the scene objective is already complete")
        player = self._player(player_id or self.active_player_id)
        path, cost = self.route_to(destination, player.player_id)
        if cost > player.moves_remaining:
            raise ValueError(
                f"destination costs {cost} move points; "
                f"only {player.moves_remaining} remain this turn"
            )
        player.position = path[-1]
        player.moves_remaining -= cost
        self.completed = destination == self.map.exit
        return cost

    def end_turn(self) -> None:
        if self.completed:
            raise ValueError("the scene objective is already complete")
        player_ids = [player.player_id for player in self.players]
        active_index = player_ids.index(self.active_player_id)
        next_index = (active_index + 1) % len(player_ids)
        if next_index == 0:
            self.turn += 1
        self.active_player_id = player_ids[next_index]
        self.active_player.moves_remaining = self.moves_per_turn

    def interact(self, player_id: str | None = None) -> MapPoint:
        player = self._player(player_id or self.active_player_id)
        point = next(
            (point for point in self.map.points if point.position == player.position),
            None,
        )
        if point is None:
            raise ValueError("there is no point of interest at the player's position")
        self.discovered_points.add(point.point_id)
        return point

    def _routes(
        self,
        start_position: Position,
        max_cost: int | None = None,
    ) -> dict[Position, int]:
        costs: dict[Position, int] = {start_position: 0}
        queue: list[tuple[int, int, int]] = [(0, *start_position)]
        while queue:
            cost, x, y = heapq.heappop(queue)
            position = (x, y)
            if cost != costs[position]:
                continue
            for neighbor in self._neighbors(position):
                step_cost = _MOVE_COST.get(self.map.tiles[neighbor[1]][neighbor[0]])
                if step_cost is None:
                    continue
                new_cost = cost + step_cost
                if max_cost is not None and new_cost > max_cost:
                    continue
                if new_cost >= costs.get(neighbor, 1_000_000):
                    continue
                costs[neighbor] = new_cost
                heapq.heappush(queue, (new_cost, *neighbor))
        return costs

    def _build_path(
        self,
        destination: Position,
        start_position: Position,
    ) -> tuple[Position, ...]:
        queue: list[tuple[int, int, int]] = [(0, *start_position)]
        costs: dict[Position, int] = {start_position: 0}
        previous: dict[Position, Position] = {}
        while queue:
            cost, x, y = heapq.heappop(queue)
            position = (x, y)
            if position == destination:
                break
            if cost != costs[position]:
                continue
            for neighbor in self._neighbors(position):
                step_cost = _MOVE_COST.get(self.map.tiles[neighbor[1]][neighbor[0]])
                if step_cost is None:
                    continue
                new_cost = cost + step_cost
                if new_cost >= costs.get(neighbor, 1_000_000):
                    continue
                costs[neighbor] = new_cost
                previous[neighbor] = position
                heapq.heappush(queue, (new_cost, *neighbor))
        path = [destination]
        while path[-1] != start_position:
            path.append(previous[path[-1]])
        path.reverse()
        return tuple(path)

    def _player(self, player_id: str) -> VttPlayer:
        player = next((item for item in self.players if item.player_id == player_id), None)
        if player is None:
            raise ValueError(f"unknown player: {player_id}")
        return player

    def _in_bounds(self, position: Position) -> bool:
        x, y = position
        return 0 <= x < self.map.width and 0 <= y < self.map.height

    def _neighbors(self, position: Position) -> tuple[Position, ...]:
        x, y = position
        return tuple(
            candidate
            for candidate in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y))
            if self._in_bounds(candidate)
        )


def generate_map(seed: str, width: int = 16, height: int = 10) -> ProceduralMap:
    seed = seed.strip()
    if not seed or len(seed) > 128:
        raise ValueError("map seed must contain 1-128 characters")
    if not 8 <= width <= 32 or not 8 <= height <= 24:
        raise ValueError("map dimensions must be width 8-32 and height 8-24")

    seed_number = int.from_bytes(sha256(seed.encode("utf-8")).digest()[:8], "big")
    rng = random.Random(seed_number)
    terrain_types: tuple[Terrain, ...] = ("field", "forest", "water", "ridge")
    weights = (48, 25, 12, 15)
    rows = [
        [rng.choices(terrain_types, weights=weights, k=1)[0] for _ in range(width)]
        for _ in range(height)
    ]

    path_y = height // 2
    start = (0, path_y)
    for x in range(width):
        previous_y = path_y
        if 0 < x < width - 1:
            path_y = min(max(path_y + rng.choice((-1, 0, 1)), 1), height - 2)
        rows[previous_y][x] = "road"
        rows[path_y][x] = "road"
    exit_y = path_y if path_y != start[1] else start[1] + 1
    rows[path_y][width - 1] = "road"
    rows[exit_y][width - 1] = "road"
    exit_position = (width - 1, exit_y)
    rows[start[1]][start[0]] = "road"

    points = _generate_points(rows, start, exit_position, rng)
    return ProceduralMap(
        seed=seed,
        width=width,
        height=height,
        tiles=tuple(tuple(row) for row in rows),
        start=start,
        exit=exit_position,
        points=points,
    )


def _generate_points(
    rows: list[list[Terrain]],
    start: Position,
    exit_position: Position,
    rng: random.Random,
) -> tuple[MapPoint, ...]:
    reachable = {start}
    frontier = [start]
    while frontier:
        x, y = frontier.pop()
        for neighbor in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            nx, ny = neighbor
            if not (0 <= ny < len(rows) and 0 <= nx < len(rows[0])):
                continue
            if neighbor in reachable or rows[ny][nx] not in _MOVE_COST:
                continue
            reachable.add(neighbor)
            frontier.append(neighbor)
    candidates = [
        (x, y)
        for y, row in enumerate(rows)
        for x, terrain in enumerate(row)
        if terrain in _MOVE_COST
        and (x, y) in reachable
        and (x, y) not in {start, exit_position}
        and min(
            abs(x - start[0]) + abs(y - start[1]),
            abs(x - exit_position[0]) + abs(y - exit_position[1]),
        )
        >= 2
    ]
    rng.shuffle(candidates)
    points: list[MapPoint] = []
    for point_id, name, kind, description in _POINT_SPECS:
        position = next(
            (
                candidate
                for candidate in candidates
                if all(
                    abs(candidate[0] - point.position[0]) + abs(candidate[1] - point.position[1])
                    >= 3
                    for point in points
                )
            ),
            candidates[0] if candidates else None,
        )
        if position is None:
            continue
        candidates.remove(position)
        points.append(MapPoint(point_id, name, kind, description, position))
    return tuple(points)


def roll_3d6(target: int) -> DiceRoll:
    if not 1 <= target <= 30:
        raise ValueError("target must be between 1 and 30")
    dice = tuple(secrets.randbelow(6) + 1 for _ in range(3))
    return DiceRoll(target=target, dice=dice, total=sum(dice))


def parse_npc_reply(raw: str) -> NpcReply:
    value = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, re.I | re.S)
    if fenced:
        value = fenced.group(1).strip()
    try:
        return NpcReply.model_validate(json.loads(value))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("NPC response must be a JSON object matching the reply schema") from exc


def parse_storyteller_reply(raw: str) -> StorytellerReply:
    value = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, re.I | re.S)
    if fenced:
        value = fenced.group(1).strip()
    try:
        return StorytellerReply.model_validate(json.loads(value))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(
            "storyteller response must be a JSON object matching the reply schema"
        ) from exc


def render_vtt_html(scene: VttScene) -> str:
    game_map = scene.map
    game = scene.game
    points_by_position = {point.position: point for point in game_map.points}
    players_by_position: dict[Position, list[VttPlayer]] = {}
    for player in game.players:
        players_by_position.setdefault(player.position, []).append(player)
    npcs_by_position: dict[Position, list[NpcActor]] = {}
    for npc in scene.npcs:
        npcs_by_position.setdefault(npc.position, []).append(npc)
    cells: list[str] = []
    for y, row in enumerate(game_map.tiles):
        for x, terrain in enumerate(row):
            position = (x, y)
            point = points_by_position.get(position)
            players = players_by_position.get(position, [])
            npcs = npcs_by_position.get(position, [])
            is_player = bool(players)
            is_active_player = any(
                player.player_id == game.active_player_id for player in players
            )
            is_exit = position == game_map.exit
            marker = (
                "P"
                if is_active_player
                else str(game.players.index(players[0]) + 1)
                if is_player
                else "E"
                if is_exit
                else "?"
                if point and point.point_id not in game.discovered_points
                else point.kind[0].upper()
                if point
                else "N"
                if npcs
                else _TERRAIN_MARKS[terrain]
            )
            description = f"{terrain}, row {chr(65 + y)}, column {x + 1}"
            if players:
                description += ", " + ", ".join(
                    f"player {player.player_name}" for player in players
                )
            if is_exit:
                description += ", exit"
            if point and point.point_id in game.discovered_points:
                description += f", {point.name}"
            if npcs:
                description += ", NPC " + ", ".join(npc.name for npc in npcs)
            classes = f"tile {terrain}"
            if is_player:
                classes += " player"
            if is_exit:
                classes += " exit"
            if point:
                classes += " point"
            if npcs:
                classes += " npc"
            cells.append(
                f'<button class="{classes}" type="button" '
                f'data-x="{x}" data-y="{y}" '
                f'aria-label="{escape(description)}" title="{escape(description)}">'
                f"{marker}</button>"
            )

    npc_html = "".join(
        '<article class="npc"><h3>'
        f"{escape(actor.name)} <small>— {escape(actor.role)} · "
        f"{escape(chr(65 + actor.position[1]) + str(actor.position[0] + 1))}</small></h3><p>"
        f"{escape(actor.personality) or 'A local character.'}</p></article>"
        for actor in scene.npcs
    ) + "".join(
        '<article class="npc"><h3>'
        f"{escape(exchange.name)} <small>— {escape(exchange.role)} · "
        f"{escape(exchange.reply.mood)}</small></h3><p>"
        f"{escape(exchange.reply.dialogue)}</p>"
        + (
            "<ul>"
            + "".join(f"<li>{escape(action)}</li>" for action in exchange.reply.suggested_actions)
            + "</ul>"
            if exchange.reply.suggested_actions
            else ""
        )
        + "</article>"
        for exchange in scene.npc_exchanges
    )
    if not npc_html:
        npc_html = '<p class="muted">No NPC conversations yet.</p>'

    character_html = "".join(
        '<article class="npc"><h3>'
        f"{escape(player.character.name)} <small>— "
        f"{escape(player.player_name)} · {escape(player.character.archetype)}</small></h3>"
        f"<p>Body {player.character.body} · Agility {player.character.agility} · "
        f"Mind {player.character.mind} · Presence {player.character.presence}</p></article>"
        for player in game.players
        if player.character is not None
    )
    if not character_html:
        character_html = '<p class="muted">No character sheets yet.</p>'

    storyteller_html = "".join(
        '<article class="npc"><p><strong>'
        f"{escape(exchange.player_name)} asked: {escape(exchange.prompt)}</strong></p>"
        f"<p>{escape(exchange.reply.narration)}</p>"
        + (
            "<ul>"
            + "".join(f"<li>{escape(choice)}</li>" for choice in exchange.reply.choices)
            + "</ul>"
            if exchange.reply.choices
            else ""
        )
        + "</article>"
        for exchange in scene.storyteller_exchanges
    )
    if not storyteller_html:
        storyteller_html = '<p class="muted">The storyteller has not narrated this scene yet.</p>'

    rules_html = (
        '<p class="muted">Ask the player helper for a concise, AI-generated rules explanation.</p>'
        if not scene.rules_help
        else f"<blockquote>{escape(scene.rules_help).replace(chr(10), '<br>')}</blockquote>"
    )
    roll_html = _render_roll(scene.last_roll)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Virtual Tabletop</title>
<style>
:root {{
  color-scheme: dark;
  font-family: system-ui, sans-serif;
  background: #08130e;
  color: #e4f5e9;
}}
body {{ margin: 0; padding: 20px; }}
h1, h2 {{ color: #75f29b; }}
.meta, .muted, small {{ color: #9ac8aa; }}
.layout {{
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(240px, 1fr);
  gap: 18px;
}}
.panel {{
  background: #102019;
  border: 1px solid #28533a;
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 14px;
}}
.map {{
  display: grid;
  grid-template-columns: repeat({game_map.width}, minmax(30px, 1fr));
  gap: 3px;
  overflow: auto;
}}
.tile {{
  aspect-ratio: 1;
  min-width: 30px;
  padding: 0;
  border: 1px solid #314d3d;
  border-radius: 4px;
  color: #effff2;
  font-size: clamp(10px, 1.5vw, 18px);
  cursor: pointer;
}}
.field {{ background: #627b50; }} .forest {{ background: #24543a; }}
.water {{ background: #28617b; }} .ridge {{ background: #75684e; }}
.road {{ background: #9a8156; }}
.tile {{ position: relative; font-weight: 700; }}
.tile:hover {{ outline: 2px solid #75f29b; z-index: 1; }}
.player {{ color: #171d0c; background: #f2d86c; border: 2px solid #fff4bb; }}
.exit {{ box-shadow: inset 0 0 0 3px #f29a64; }}
.point {{ color: #fff3bd; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 8px 16px; color: #b6d2bd; }}
.legend b {{ color: #efffdd; }}
.npc {{ border-top: 1px solid #28533a; padding-top: 8px; }}
blockquote {{ border-left: 3px solid #75f29b; margin: 8px 0; padding: 8px 12px; }}
#tile-status {{ min-height: 1.5em; color: #9ac8aa; }}
@media (max-width: 760px) {{ .layout {{ grid-template-columns: 1fr; }} .map {{ gap: 2px; }} }}
</style>
</head>
<body>
<h1>Virtual Tabletop</h1>
<p class="meta">Seed: {escape(game_map.seed)} · {game_map.width} ×
{game_map.height} · Turn {game.turn} · Active player: {escape(game.active_player.player_name)} ·
Player at {game.player_label} · {game.moves_remaining}/{game.moves_per_turn} move points ·
{"Exit reached" if game.completed else "Reach E to complete the scene"} ·
P = player · E = exit · ? = undiscovered location</p>
<div class="layout">
<main>
<section class="panel">
<h2>Scene board</h2>
<div class="map" role="group" aria-label="Generated tabletop map">{"".join(cells)}</div>
<p class="legend">
<span><b>F</b> open ground · 1 MP</span>
<span><b>T</b> forest · 2 MP</span>
<span><b>·</b> road · 1 MP</span>
<span><b>W</b> water · blocked</span>
<span><b>R</b> ridge · blocked</span>
<span><b>?</b> undiscovered location</span>
</p>
<p id="tile-status" aria-live="polite">Playable movement is available in the
live VTT panel. Snapshots show the saved board position.</p>
</section>
<section class="panel"><h2>Player helper</h2>{roll_html}{rules_html}</section>
<section class="panel"><h2>Storyteller</h2>{storyteller_html}</section>
</main>
<aside>
<section class="panel"><h2>Characters</h2>{character_html}</section>
<section class="panel"><h2>NPCs</h2>{npc_html}</section>
<section class="panel">
<h2>Table notes</h2>
<p>AI-generated dialogue and rules summaries are suggestions, not official
rules text. Confirm rulings with the game master and your rulebooks.</p>
</section>
</aside>
</div>
<script>
document.querySelectorAll(".tile").forEach((tile) => {{
  tile.addEventListener("click", () => {{
    document.getElementById("tile-status").textContent =
      "Tile " + String.fromCharCode(65 + Number(tile.dataset.y)) +
      (Number(tile.dataset.x) + 1) + " — " +
      tile.getAttribute("aria-label");
  }});
}});
</script>
</body>
</html>"""


def _render_roll(roll: DiceRoll | None) -> str:
    if roll is None:
        return '<p class="muted">No roll yet.</p>'
    result = "Success" if roll.success else "Failure"
    margin_type = "by" if roll.success else "missed by"
    return (
        f"<p><strong>{result} {margin_type} {roll.margin}.</strong> "
        f"Rolled {roll.dice[0]} + {roll.dice[1]} + {roll.dice[2]} = "
        f"{roll.total} against target {roll.target}.</p>"
    )
