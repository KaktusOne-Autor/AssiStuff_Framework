from __future__ import annotations

import json
import tempfile
import unittest
from html import escape
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from assistuff.visual.vtt import (
    NpcActor,
    StorytellerExchange,
    StorytellerReply,
    VttCharacter,
    VttCharacterStore,
    VttGame,
    VttScene,
    generate_map,
    render_vtt_html,
)
from assistuff.visual.vtt_host import VttHostServer


class VttGameplayTests(unittest.TestCase):
    def test_lan_host_join_turn_actions_and_leave(self) -> None:
        scene = VttScene(map=generate_map("lan-play"))

        class FakeDispatcher:
            async def final_text(self, prompt: str) -> str:
                if "Roleplay one original tabletop NPC." in prompt:
                    return json.dumps(
                        {"dialogue": "The trail bends east.", "mood": "helpful"}
                    )
                return json.dumps(
                    {
                        "narration": "A lantern appears beyond the trees.",
                        "choices": ["Follow the light"],
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
                    "A lantern appears beyond the trees.",
                )

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

        path, _ = game.route_to(point.position)
        for destination in path[1:]:
            while destination not in game.reachable_costs():
                game.end_turn()
            game.move_to(destination)

        discovered = game.interact()
        self.assertEqual(discovered, point)
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


if __name__ == "__main__":
    unittest.main()
