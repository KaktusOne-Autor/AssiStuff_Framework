from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from html import escape
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from assistuff.visual.vtt import (
    AddNpcUpdate,
    DiceRoll,
    NpcActor,
    RevealLocationUpdate,
    SetObjectiveUpdate,
    StorytellerExchange,
    StorytellerReply,
    VttCharacter,
    VttCharacterStore,
    VttGame,
    VttScene,
    apply_gm_updates,
    empty_map,
    generate_map,
    generate_storyteller_reply,
    parse_ai_map,
    render_vtt_html,
    render_vtt_svg,
)
from assistuff.visual.vtt_host import VttHostError, VttHostServer


class VttGameplayTests(unittest.TestCase):
    def test_lan_host_join_turn_actions_and_leave(self) -> None:
        scene = VttScene(map=generate_map("lan-play"))

        class FakeDispatcher:
            async def final_text(self, prompt: str) -> str:
                if "Roleplay one original tabletop NPC." in prompt:
                    return json.dumps(
                        {"dialogue": "The trail bends east.", "mood": "helpful"}
                    )
                if "You are the active game master" in prompt:
                    return json.dumps(
                        {
                            "narration": "A lantern appears beyond the trees.",
                            "choices": [],
                            "check": {
                                "skill": "Observation",
                                "attribute": "mind",
                                "difficulty_modifier": 0,
                                "reason": "The party looks for a sign.",
                            },
                        }
                    )
                return json.dumps(
                    {
                        "narration": "The lantern reveals the old camp.",
                        "choices": ["Search the ashes"],
                        "updates": [
                            {"action": "reveal_location", "point_id": "camp"}
                        ],
                        "chronicle_entry": "The old camp was found.",
                    }
                )

        with tempfile.TemporaryDirectory() as directory:
            host = VttHostServer(
                lambda: scene,
                dispatcher=FakeDispatcher(),
                character_store=VttCharacterStore(
                    Path(directory) / "characters.json"
                ),
                on_change=lambda: None,
            )
            urls = host.start(0)
            self.assertTrue(urls)
            base_url = urls[0]

            def request(path: str, payload=None, token: str | None = None):
                headers = {}
                data = None
                if payload is not None:
                    data = json.dumps(payload).encode("utf-8")
                    headers["Content-Type"] = "application/json"
                if token:
                    headers["X-AssiStuff-Token"] = token
                req = Request(base_url + path, data=data, headers=headers)
                try:
                    with urlopen(req, timeout=3) as response:
                        return response.status, json.loads(response.read())
                except HTTPError as exc:
                    return exc.code, json.loads(exc.read())

            try:
                status, error = request(
                    "/api/join",
                    {
                        "join_code": "wrong",
                        "player_name": "Ari",
                        "character": {"name": "Mira"},
                    },
                )
                self.assertEqual(status, 400)
                self.assertIn("join code", error["error"])

                status, joined = request(
                    "/api/join",
                    {
                        "join_code": host.join_code,
                        "player_name": "Ari",
                        "character": {"name": "Mira"},
                    },
                )
                self.assertEqual(status, 200)
                token = joined["token"]
                self.assertIn("<svg", host.illustration_for(token))
                with self.assertRaisesRegex(VttHostError, "session is not valid"):
                    host.illustration_for("invalid")
                illustration_request = Request(
                    base_url + "/api/map.svg",
                    headers={"X-AssiStuff-Token": token},
                )
                with urlopen(illustration_request, timeout=3) as response:
                    self.assertIn("image/svg+xml", response.headers["Content-Type"])
                    self.assertIn(b"<svg", response.read())

                status, error = request(
                    "/api/action",
                    {"action": "end_turn"},
                    token,
                )
                self.assertEqual(status, 400)
                self.assertIn("not your turn", error["error"])

                scene.game.end_turn()
                status, state = request("/api/state", token=token)
                self.assertEqual(status, 200)
                self.assertEqual(state["active_player_id"], joined["player_id"])
                self.assertTrue(state["reachable"])
                destination = state["reachable"][0]
                status, result = request(
                    "/api/action",
                    {
                        "action": "move",
                        "x": destination["x"],
                        "y": destination["y"],
                    },
                    token,
                )
                self.assertEqual(status, 200)
                self.assertTrue(result["ok"])
                status, state = request("/api/state", token=token)
                self.assertEqual(
                    state["players"][1]["position"],
                    [destination["x"], destination["y"]],
                )

                scene.npcs.append(
                    NpcActor("Mara", "scout", tuple(state["players"][1]["position"]))
                )
                status, result = request(
                    "/api/action",
                    {
                        "action": "npc",
                        "npc_id": scene.npcs[0].npc_id,
                        "message": "Where is the trail?",
                    },
                    token,
                )
                self.assertEqual(status, 200)
                self.assertTrue(result["ok"])
                self.assertEqual(scene.npc_exchanges[-1].reply.dialogue, "The trail bends east.")

                status, result = request(
                    "/api/action",
                    {"action": "storyteller", "message": "What happens next?"},
                    token,
                )
                self.assertEqual(status, 200)
                self.assertTrue(result["ok"])
                self.assertEqual(
                    scene.storyteller_exchanges[-1].reply.narration,
                    "The lantern reveals the old camp.",
                )
                self.assertTrue(scene.storyteller_exchanges[-1].reply.check_result)
                self.assertIn("camp", scene.game.discovered_points)
                self.assertIn("old camp was found", scene.chronicle[-1].text)

                scene.game.end_turn()
                status, result = request("/api/leave", {}, token)
                self.assertEqual(status, 200)
                self.assertTrue(result["ok"])
                self.assertEqual(scene.game.active_player_id, "host")
                status, error = request("/api/state", token=token)
                self.assertEqual(status, 401)
                self.assertIn("join the host", error["error"])
            finally:
                host.stop()

    def test_map_and_locations_are_seeded_and_reachable(self) -> None:
        first = generate_map("playtest")
        second = generate_map("playtest")

        self.assertEqual(first.tiles, second.tiles)
        self.assertEqual(first.points, second.points)
        self.assertEqual(len(first.points), 3)
        game = VttGame(first)
        for point in first.points:
            path, _ = game.route_to(point.position)
            self.assertEqual(path[0], first.start)
            self.assertEqual(path[-1], point.position)

    def test_ai_map_response_creates_reachable_campaign_scene(self) -> None:
        payload = self._ai_map_payload()
        game_map, npcs, history = parse_ai_map(
            json.dumps(payload),
            seed="ai-campaign",
            width=8,
            height=8,
        )

        self.assertEqual(game_map.title, "The Glass Marsh")
        self.assertEqual(game_map.objective, "Find the missing bell.")
        self.assertTrue(game_map.ready)
        self.assertEqual(len(game_map.points), 2)
        self.assertEqual(npcs[0].name, "Sella")
        self.assertEqual(history.timeline[0], "The marsh bells were forged.")
        self.assertIn(game_map.exit, VttGame(game_map)._routes(game_map.start))

    def test_ai_map_response_rejects_disconnected_important_locations(self) -> None:
        payload = self._ai_map_payload()
        for row in payload["tiles"]:
            row[3] = "water"

        with self.assertRaisesRegex(ValueError, "reachable"):
            parse_ai_map(
                json.dumps(payload),
                seed="blocked-ai-map",
                width=8,
                height=8,
            )

    def test_unbuilt_map_cannot_be_played(self) -> None:
        game = VttGame(empty_map())

        with self.assertRaisesRegex(ValueError, "AI map"):
            game.move_to((1, 0))

        with tempfile.TemporaryDirectory() as directory:
            host = VttHostServer(
                lambda: VttScene(map=empty_map()),
                dispatcher=None,
                character_store=VttCharacterStore(Path(directory) / "characters.json"),
                on_change=lambda: None,
            )
            with self.assertRaisesRegex(VttHostError, "build an AI map"):
                host.start(0)

    def test_game_master_updates_are_validated_before_mutation(self) -> None:
        scene = VttScene(map=generate_map("gm-updates"))
        point = scene.map.points[0]
        npc_position = next(
            (x, y)
            for y, row in enumerate(scene.map.tiles)
            for x, terrain in enumerate(row)
            if terrain not in {"water", "ridge"}
            and (x, y) not in {
                scene.map.start,
                scene.map.exit,
                *(point.position for point in scene.map.points),
            }
        )
        updates = [
            RevealLocationUpdate(action="reveal_location", point_id=point.point_id),
            SetObjectiveUpdate(action="set_objective", objective="Reach the bell."),
            AddNpcUpdate(
                action="add_npc",
                name="Sella",
                role="marsh guide",
                position={"x": npc_position[0], "y": npc_position[1]},
            ),
        ]
        applied = apply_gm_updates(scene, updates)

        self.assertIn(point.point_id, scene.game.discovered_points)
        self.assertEqual(scene.current_objective, "Reach the bell.")
        self.assertEqual(scene.npcs[0].name, "Sella")
        self.assertEqual(len(applied), 3)

        invalid = [
            RevealLocationUpdate(action="reveal_location", point_id=scene.map.points[1].point_id),
            AddNpcUpdate(
                action="add_npc",
                name="Blocked",
                role="test",
                position={
                    "x": scene.game.player_position[0],
                    "y": scene.game.player_position[1],
                },
            ),
        ]
        before = set(scene.game.discovered_points)
        with self.assertRaisesRegex(ValueError, "overlap a player"):
            apply_gm_updates(scene, invalid)
        self.assertEqual(scene.game.discovered_points, before)

    def test_active_game_master_resolves_only_the_host_rolled_check(self) -> None:
        class FakeDispatcher:
            prompts: list[str] = []

            async def final_text(self, prompt: str) -> str:
                self.prompts.append(prompt)
                if len(self.prompts) == 1:
                    return json.dumps(
                        {
                            "narration": "The tracks disappear in the rain.",
                            "choices": [],
                            "check": {
                                "skill": "Tracking",
                                "attribute": "mind",
                                "difficulty_modifier": 0,
                                "reason": "The party searches for the trail.",
                            },
                        }
                    )
                return json.dumps(
                    {
                        "narration": "You find a fresh trail beneath the reeds.",
                        "choices": ["Follow it"],
                        "chronicle_entry": "The party found a trail.",
                    }
                )

        character = VttCharacter(
            name="Mira",
            player_name="Ari",
            mind=3,
            skills={"Tracking": 2},
        )
        dispatcher = FakeDispatcher()
        with patch(
            "assistuff.visual.vtt.roll_3d6",
            return_value=DiceRoll(target=16, dice=(2, 2, 2), total=6),
        ):
            reply, roll = asyncio.run(
                generate_storyteller_reply(
                    dispatcher,
                    {"turn": 1, "active_player": "Ari"},
                    "Search for tracks.",
                    character,
                )
            )

        self.assertEqual(len(dispatcher.prompts), 2)
        self.assertIn("2 + 2 + 2 = 6; success", dispatcher.prompts[1])
        self.assertEqual(roll.target, 16)
        self.assertIn("success by 10", reply.check_result)
        self.assertEqual(reply.narration, "You find a fresh trail beneath the reeds.")
        self.assertEqual(reply.chronicle_entry, "The party found a trail.")

    @staticmethod
    def _ai_map_payload() -> dict:
        return {
            "title": "The Glass Marsh",
            "region": "The Drowned Fen",
            "description": "Reeds gather around a chain of silver pools.",
            "objective": "Find the missing bell.",
            "history": {
                "title": "The Bell of Glass",
                "premise": "A lost bell is said to calm the marsh.",
                "world_history": "The marsh bells were forged.",
                "current_conflict": "The last bell has gone silent.",
                "timeline": [
                    "The marsh bells were forged.",
                    "The old causeway sank.",
                ],
            },
            "tiles": [["field" for _ in range(8)] for _ in range(8)],
            "start": {"x": 0, "y": 0},
            "exit": {"x": 7, "y": 7},
            "points": [
                {
                    "point_id": "sunken-arch",
                    "name": "Sunken Arch",
                    "kind": "ruin",
                    "description": "A stone arch rises from the water.",
                    "position": {"x": 2, "y": 2},
                },
                {
                    "point_id": "bell-pool",
                    "name": "Bell Pool",
                    "kind": "landmark",
                    "description": "A silver bell lies below the surface.",
                    "position": {"x": 4, "y": 4},
                },
            ],
            "npcs": [
                {
                    "name": "Sella",
                    "role": "marsh guide",
                    "personality": "Patient and superstitious.",
                    "position": {"x": 6, "y": 2},
                }
            ],
        }

    def test_move_budget_blocks_long_moves_until_next_turn(self) -> None:
        game = VttGame(generate_map("movement"))
        route, total_cost = game.route_to(game.map.exit)
        self.assertGreater(total_cost, game.moves_remaining)
        self.assertEqual(route[0], game.player_position)
        self.assertEqual(route[-1], game.map.exit)
        with self.assertRaisesRegex(ValueError, "only .* remain"):
            game.move_to(game.map.exit)

        reachable, cost = next(
            (position, cost) for position, cost in game.reachable_costs().items() if cost > 0
        )
        self.assertEqual(game.move_to(reachable), cost)
        self.assertEqual(game.player_position, reachable)
        self.assertEqual(game.moves_remaining, game.moves_per_turn - cost)
        game.end_turn()
        self.assertEqual(game.turn, 2)
        self.assertEqual(game.moves_remaining, game.moves_per_turn)

    def test_blocked_terrain_cannot_be_entered(self) -> None:
        game = VttGame(generate_map("blocked"))
        blocked = next(
            (x, y)
            for y, row in enumerate(game.map.tiles)
            for x, terrain in enumerate(row)
            if terrain in {"water", "ridge"}
        )
        with self.assertRaisesRegex(ValueError, "cannot be crossed"):
            game.route_to(blocked)

    def test_reaching_exit_completes_scene(self) -> None:
        game = VttGame(generate_map("objective"))
        path, _ = game.route_to(game.map.exit)
        for destination in path[1:]:
            while destination not in game.reachable_costs():
                game.end_turn()
            game.move_to(destination)

        self.assertTrue(game.completed)
        self.assertEqual(game.player_position, game.map.exit)
        self.assertEqual(game.reachable_costs(), {})
        with self.assertRaisesRegex(ValueError, "already complete"):
            game.end_turn()
        with self.assertRaisesRegex(ValueError, "already complete"):
            game.move_to(game.map.start)

    def test_interaction_requires_player_at_location_and_updates_snapshot(self) -> None:
        scene = VttScene(map=generate_map("discovery"))
        game = scene.game
        point = scene.map.points[0]
        with self.assertRaisesRegex(ValueError, "no point of interest"):
            game.interact()
        illustration = render_vtt_svg(scene)
        self.assertNotIn(point.name, illustration)

        path, _ = game.route_to(point.position)
        for destination in path[1:]:
            while destination not in game.reachable_costs():
                game.end_turn()
            game.move_to(destination)

        discovered = game.interact()
        self.assertEqual(discovered, point)
        self.assertIn(escape(point.name), render_vtt_svg(scene))
        self.assertIn(point.point_id, game.discovered_points)
        html = render_vtt_html(scene)
        self.assertIn(f"Player at {game.player_label}", html)
        self.assertIn(escape(point.name), html)
        self.assertIn("move points", html)

    def test_seed_and_dimensions_are_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "seed"):
            generate_map(" ")
        with self.assertRaisesRegex(ValueError, "dimensions"):
            generate_map("valid", width=7)

    def test_character_point_buy_and_skill_target(self) -> None:
        character = VttCharacter(
            name="Rin",
            player_name="Player",
            body=2,
            agility=3,
            mind=4,
            presence=2,
            skills={"Tracking": 2},
        )
        self.assertEqual(character.attribute_points_spent, 15)
        self.assertEqual(character.skill_points_spent, 4)
        self.assertEqual(character.skill_target("Tracking", "mind"), 18)
        with self.assertRaisesRegex(ValueError, "budget is 40"):
            VttCharacter(
                name="Overbuilt",
                player_name="Player",
                body=5,
                agility=5,
                mind=5,
                presence=5,
            )

    def test_hotseat_players_have_separate_positions_and_turns(self) -> None:
        game = VttGame(generate_map("hotseat"))
        first = VttCharacter(name="Mira", player_name="Ari")
        second = VttCharacter(name="Tov", player_name="Bo")
        first_player = game.add_player("player-one", first)
        second_player = game.add_player("player-two", second)
        self.assertNotEqual(first_player.position, second_player.position)

        game.end_turn()
        self.assertEqual(game.active_player_id, "player-one")
        target = next(iter(game.reachable_costs()))
        game.move_to(target)
        self.assertEqual(first_player.position, target)
        self.assertNotEqual(second_player.position, target)
        game.end_turn()
        self.assertEqual(game.active_player_id, "player-two")
        game.end_turn()
        self.assertEqual(game.active_player_id, "host")
        self.assertEqual(game.turn, 2)

    def test_character_store_round_trip_uses_private_file_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile" / "vtt" / "characters.json"
            store = VttCharacterStore(path)
            character = VttCharacter(
                name="Nia",
                player_name="Player",
                backstory="A courier who follows old roads.",
                skills={"First Aid": 2},
            )
            store.save(character)
            self.assertEqual(store.load(), [character])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_npc_and_storyteller_are_rendered_as_escaped_scene_data(self) -> None:
        scene = VttScene(map=generate_map("actors"))
        scene.npcs.append(
            NpcActor(
                name="<script>alert(1)</script>",
                role="guide",
                position=scene.map.start,
                personality="A quiet guide.",
            )
        )
        scene.storyteller_exchanges.append(
            StorytellerExchange(
                "Player",
                "Look around",
                StorytellerReply(
                    narration="The lantern flickers.",
                    choices=["Follow the trail"],
                ),
            )
        )
        html = render_vtt_html(scene)
        self.assertIn("NPCs", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("The lantern flickers.", html)
        svg = render_vtt_svg(scene)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", svg)
        self.assertNotIn("<script>alert(1)</script>", svg)


if __name__ == "__main__":
    unittest.main()
