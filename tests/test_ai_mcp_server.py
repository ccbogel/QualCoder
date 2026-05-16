import json
import os
import sqlite3
import tempfile
from types import SimpleNamespace
from unittest import TestCase

from qualcoder.ai_mcp_server import AiMcpServer


class TestAiMcpServer(TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path = self.temp_dir.name
        self.db_path = os.path.join(self.project_path, "data.qda")
        self.conn = sqlite3.connect(self.db_path)
        cur = self.conn.cursor()

        cur.execute(
            "CREATE TABLE project (databaseversion text, date text, memo text, about text, "
            "bookmarkfile integer, bookmarkpos integer, codername text, recently_used_codes text)"
        )
        cur.execute(
            "CREATE TABLE source (id integer primary key, name text, fulltext text, mediapath text, "
            "memo text, owner text, date text, av_text_id integer, risid integer, unique(name))"
        )
        cur.execute(
            "CREATE TABLE code_cat (catid integer primary key, name text, owner text, date text, memo text, "
            "supercatid integer, unique(name))"
        )
        cur.execute(
            "CREATE TABLE code_name (cid integer primary key, name text, memo text, catid integer, owner text, "
            "date text, color text, unique(name))"
        )
        cur.execute(
            "CREATE TABLE code_text (ctid integer primary key, cid integer, fid integer, seltext text, pos0 integer, "
            "pos1 integer, owner text, date text, memo text, avid integer, important integer)"
        )
        cur.execute(
            "CREATE TABLE coder_names (name text unique not null, visibility integer not null default 1 "
            "check (visibility in (0, 1)))"
        )
        cur.execute(
            "CREATE TABLE journal (jid integer primary key, name text, jentry text, date text, owner text, unique(name))"
        )

        cur.execute(
            "INSERT INTO project VALUES(?,?,?,?,?,?,?,?)",
            ("v11", "2026-02-13", "memo text", "about", 0, 0, "default", ""),
        )
        cur.execute(
            "INSERT INTO source (id, name, fulltext, mediapath, memo, owner, date, av_text_id, risid) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (1, "doc one", "abcdefghij", None, "doc memo", "default", "2026-02-13", None, None),
        )
        cur.execute(
            "INSERT INTO source (id, name, fulltext, mediapath, memo, owner, date, av_text_id, risid) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (2, "doc two", "first line\nsecond line\nthird line\nfourth", None, "doc memo 2", "default", "2026-02-13", None, None),
        )
        cur.execute(
            "INSERT INTO source (id, name, fulltext, mediapath, memo, owner, date, av_text_id, risid) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (3, "doc three", "uvwxyz", None, "doc memo 3", "default", "2026-02-13", None, None),
        )
        cur.execute(
            "INSERT INTO source (id, name, fulltext, mediapath, memo, owner, date, av_text_id, risid) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (4, "doc four", "line1\nline2\nline3\nline4", None, "doc memo 4", "default", "2026-02-13", None, None),
        )
        cur.execute(
            "INSERT INTO code_cat (catid, name, owner, date, memo, supercatid) VALUES (?,?,?,?,?,?)",
            (1, "cat one", "default", "2026-02-13", "cat memo", None),
        )
        cur.execute(
            "INSERT INTO code_cat (catid, name, owner, date, memo, supercatid) VALUES (?,?,?,?,?,?)",
            (2, "\U0001F4CC Speakers", "default", "2026-02-13", "speaker memo", None),
        )
        cur.execute(
            "INSERT INTO code_cat (catid, name, owner, date, memo, supercatid) VALUES (?,?,?,?,?,?)",
            (3, "cat child", "default", "2026-02-13", "child memo", 1),
        )
        cur.execute(
            "INSERT INTO code_name (cid, name, memo, catid, owner, date, color) VALUES (?,?,?,?,?,?,?)",
            (1, "code one", "code memo", 1, "default", "2026-02-13", "#AAAAAA"),
        )
        cur.execute(
            "INSERT INTO code_name (cid, name, memo, catid, owner, date, color) VALUES (?,?,?,?,?,?,?)",
            (2, "code child", "child code memo", 3, "default", "2026-02-13", "#BBBBBB"),
        )
        cur.execute(
            "INSERT INTO journal (jid, name, jentry, date, owner) VALUES (?,?,?,?,?)",
            (1, "journal one", "journal body", "2026-02-13", "default"),
        )
        cur.executemany(
            "INSERT INTO coder_names (name, visibility) VALUES (?,?)",
            [
                ("default", 1),
                ("hidden_user", 0),
            ],
        )
        cur.executemany(
            "INSERT INTO code_text (ctid, cid, fid, seltext, pos0, pos1, owner, date, memo, avid, important) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                (1, 1, 1, "alpha", 0, 5, "default", "2026-02-10", "", None, 0),
                (2, 1, 2, "beta quote", 0, 10, "default", "2026-02-12", "", None, 0),
                (3, 1, 3, "gamma", 0, 5, "default", "2026-02-11", "", None, 0),
                (4, 1, 1, "delta", 6, 11, "default", "2026-02-13", "", None, 0),
                (5, 1, 2, "epsilon", 11, 18, "default", "2026-02-09", "", None, 0),
                (6, 1, 2, "hidden quote", 20, 31, "hidden_user", "2026-02-14", "", None, 0),
                (7, 2, 1, "cde", 2, 5, "default", "2026-02-15", "", None, 0),
            ],
        )
        cur.execute(
            "CREATE VIEW code_text_visible AS "
            "SELECT code_text.* FROM code_text "
            "JOIN coder_names ON code_text.owner = coder_names.name "
            "WHERE coder_names.visibility = 1"
        )
        self.conn.commit()

        self.ai_recorded_changes = []

        def _record_ai_change(change_set_id, operation):
            self.ai_recorded_changes.append((change_set_id, operation))

        self.app = SimpleNamespace(
            project_path=self.project_path,
            project_name="test_project.qda",
            settings={"codername": "default"},
            conn=self.conn,
            ai=SimpleNamespace(record_ai_change=_record_ai_change),
        )
        self.server = AiMcpServer(self.app)

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_initialize(self):
        res = self.server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertIn("result", res)
        self.assertEqual("2025-06-18", res["result"]["protocolVersion"])
        self.assertIn("resources", res["result"]["capabilities"])
        self.assertIn("QualCoder", res["result"]["instructions"])
        self.assertIn("tools/call", res["result"]["instructions"])

    def test_tools_list_contains_create_tools(self):
        res = self.server.handle_request({"jsonrpc": "2.0", "id": 30, "method": "tools/list", "params": {}})
        self.assertIn("result", res)
        names = [tool["name"] for tool in res["result"]["tools"]]
        self.assertIn("codes/create_category", names)
        self.assertIn("codes/create_code", names)
        self.assertIn("codes/create_text_coding", names)
        self.assertIn("codes/preview_delete_category", names)
        self.assertIn("codes/preview_delete_code", names)
        self.assertIn("codes/rename_code", names)
        self.assertIn("codes/delete_text_coding", names)
        self.assertNotIn("codes/preview_move_category", names)
        self.assertNotIn("codes/preview_move_code", names)

    def test_tool_create_category(self):
        req = {
            "jsonrpc": "2.0",
            "id": 31,
            "method": "tools/call",
            "params": {
                "name": "codes/create_category",
                "arguments": {"name": "cat ai", "memo": "created by ai"},
                "_ai_change_set_id": "run-1",
            },
        }
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        payload = res["result"]["structuredContent"]
        self.assertTrue(payload["created"])
        self.assertEqual("AI Agent", payload["category"]["owner"])
        self.assertTrue(len(self.ai_recorded_changes) > 0)
        self.assertEqual("create_category", self.ai_recorded_changes[0][1]["type"])

    def test_tool_create_code(self):
        req = {
            "jsonrpc": "2.0",
            "id": 32,
            "method": "tools/call",
            "params": {
                "name": "codes/create_code",
                "arguments": {"name": "code ai", "memo": "m", "catid": 1, "color": "#ABCDEF"},
                "_ai_change_set_id": "run-2",
            },
        }
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        payload = res["result"]["structuredContent"]
        self.assertTrue(payload["created"])
        self.assertEqual("AI Agent", payload["code"]["owner"])
        self.assertEqual("#ABCDEF", payload["code"]["color"])

    def test_tool_create_text_coding(self):
        req = {
            "jsonrpc": "2.0",
            "id": 33,
            "method": "tools/call",
            "params": {
                "name": "codes/create_text_coding",
                "arguments": {"cid": 1, "fid": 1, "quote": "bcd", "memo": "ai coding"},
                "_ai_change_set_id": "run-3",
            },
        }
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        payload = res["result"]["structuredContent"]
        self.assertTrue(payload["created"])
        self.assertEqual("AI Agent", payload["coding"]["owner"])
        self.assertEqual("bcd", payload["coding"]["quote"])

    def test_write_tools_return_error_when_ai_permissions_are_read_only(self):
        self.app.settings["ai_permissions"] = 0

        for tool_name, arguments in (
            ("codes/create_category", {"name": "cat blocked"}),
            ("codes/create_code", {"name": "code blocked"}),
            ("codes/create_text_coding", {"cid": 1, "fid": 1, "quote": "bcd"}),
        ):
            with self.subTest(tool_name=tool_name):
                req = {
                    "jsonrpc": "2.0",
                    "id": 40,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments,
                        "_ai_change_set_id": "blocked-run",
                    },
                }
                res = self.server.handle_request(req)
                self.assertIn("result", res)
                self.assertTrue(res["result"]["isError"])
                payload = res["result"]["structuredContent"]
                self.assertEqual(tool_name, payload["tool"])
                self.assertEqual("ai_permissions_denied", payload["error"]["code"])
                self.assertIn("Sandboxed", payload["error"]["message"])
                self.assertIn("Full access", payload["error"]["message"])
                self.assertIn("Read-only", payload["error"]["message"])

        self.assertEqual([], self.ai_recorded_changes)

    def test_full_access_tools_return_error_when_ai_permissions_are_sandboxed(self):
        self.app.settings["ai_permissions"] = 1
        req = {
            "jsonrpc": "2.0",
            "id": 41,
            "method": "tools/call",
            "params": {
                "name": "codes/rename_code",
                "arguments": {"cid": 1, "new_name": "code renamed"},
            },
        }
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        self.assertTrue(res["result"]["isError"])
        payload = res["result"]["structuredContent"]
        self.assertEqual("ai_permissions_denied", payload["error"]["code"])
        self.assertIn("Full access", payload["error"]["message"])

    def test_full_access_rename_code(self):
        self.app.settings["ai_permissions"] = 2
        req = {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "tools/call",
            "params": {
                "name": "codes/rename_code",
                "arguments": {"cid": 1, "new_name": "code renamed"},
                "_ai_change_set_id": "run-rename",
            },
        }
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        payload = res["result"]["structuredContent"]
        self.assertTrue(payload["renamed"])
        self.assertEqual("code renamed", payload["code"]["new_name"])
        self.assertEqual("rename_code", self.ai_recorded_changes[-1][1]["type"])

    def test_full_access_move_category_without_preview(self):
        self.app.settings["ai_permissions"] = 2
        req = {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "tools/call",
            "params": {
                "name": "codes/move_category",
                "arguments": {"catid": 3, "new_supercatid": 2},
                "_ai_change_set_id": "run-move-category",
            },
        }
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        payload = res["result"]["structuredContent"]
        self.assertTrue(payload["moved"])
        cur = self.conn.cursor()
        cur.execute("SELECT supercatid FROM code_cat WHERE catid=3")
        self.assertEqual(2, cur.fetchone()[0])
        self.assertEqual("move_category_tree", self.ai_recorded_changes[-1][1]["type"])

    def test_full_access_move_code_without_preview(self):
        self.app.settings["ai_permissions"] = 2
        req = {
            "jsonrpc": "2.0",
            "id": 43,
            "method": "tools/call",
            "params": {
                "name": "codes/move_code",
                "arguments": {"cid": 1, "new_catid": 2},
                "_ai_change_set_id": "run-move-code",
            },
        }
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        payload = res["result"]["structuredContent"]
        self.assertTrue(payload["moved"])
        cur = self.conn.cursor()
        cur.execute("SELECT catid FROM code_name WHERE cid=1")
        self.assertEqual(2, cur.fetchone()[0])
        self.assertEqual("move_code", self.ai_recorded_changes[-1][1]["type"])

    def test_preview_and_delete_category_tree(self):
        self.app.settings["ai_permissions"] = 2
        preview_req = {
            "jsonrpc": "2.0",
            "id": 44,
            "method": "tools/call",
            "params": {
                "name": "codes/preview_delete_category",
                "arguments": {"catid": 1},
            },
        }
        preview_res = self.server.handle_request(preview_req)
        self.assertIn("result", preview_res)
        preview_payload = preview_res["result"]["structuredContent"]
        self.assertEqual(2, preview_payload["impact"]["counts"]["categories"])
        self.assertEqual(2, preview_payload["impact"]["counts"]["codes"])
        self.assertEqual(7, preview_payload["impact"]["counts"]["total_codings"])
        preview_token = preview_payload["preview_token"]
        self.assertTrue(isinstance(preview_token, str))
        self.assertTrue(len(preview_token) > 10)

        delete_req = {
            "jsonrpc": "2.0",
            "id": 45,
            "method": "tools/call",
            "params": {
                "name": "codes/delete_category",
                "arguments": {"catid": 1, "preview_token": preview_token},
                "_ai_change_set_id": "run-delete-tree",
            },
        }
        delete_res = self.server.handle_request(delete_req)
        self.assertIn("result", delete_res)
        delete_payload = delete_res["result"]["structuredContent"]
        self.assertTrue(delete_payload["deleted"])
        cur = self.conn.cursor()
        cur.execute("SELECT count(*) FROM code_cat WHERE catid IN (1,3)")
        self.assertEqual(0, cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM code_name WHERE cid IN (1,2)")
        self.assertEqual(0, cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM code_text WHERE cid IN (1,2)")
        self.assertEqual(0, cur.fetchone()[0])
        self.assertEqual("delete_category_tree", self.ai_recorded_changes[-1][1]["type"])

    def test_full_access_move_text_coding(self):
        self.app.settings["ai_permissions"] = 2
        req = {
            "jsonrpc": "2.0",
            "id": 46,
            "method": "tools/call",
            "params": {
                "name": "codes/move_text_coding",
                "arguments": {"ctid": 1, "new_cid": 2},
                "_ai_change_set_id": "run-move-coding",
            },
        }
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        payload = res["result"]["structuredContent"]
        self.assertTrue(payload["moved"])
        cur = self.conn.cursor()
        cur.execute("SELECT cid FROM code_text WHERE ctid=1")
        self.assertEqual(2, cur.fetchone()[0])
        self.assertEqual("move_coding_text", self.ai_recorded_changes[-1][1]["type"])

    def test_codes_tree_contains_structure_rules_and_speaker_convention(self):
        req = {"jsonrpc": "2.0", "id": 9, "method": "resources/read", "params": {"uri": "qualcoder://codes/tree"}}
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        payload = json.loads(res["result"]["contents"][0]["text"])
        self.assertIn("structure_rules", payload)
        self.assertIn("special_conventions", payload)
        self.assertTrue(payload["structure_rules"]["codes_are_leaves"])
        self.assertFalse(payload["structure_rules"]["codes_can_have_subcodes"])
        self.assertTrue(payload["structure_rules"]["categories_can_contain_codes"])
        self.assertEqual("\U0001F4CC ", payload["special_conventions"]["speaker_category_prefix"])
        self.assertTrue(payload["special_conventions"]["speaker_category_present"])
        self.assertIn(2, payload["special_conventions"]["speaker_category_ids"])

    def test_resources_templates_include_code_segments_template(self):
        res = self.server.handle_request({"jsonrpc": "2.0", "id": 21, "method": "resources/templates/list", "params": {}})
        self.assertIn("result", res)
        templates = [r["uriTemplate"] for r in res["result"]["resourceTemplates"]]
        self.assertIn("qualcoder://codes/segments/{cid}", templates)
        self.assertIn("qualcoder://vector/search{?q,cursor,file_ids,exclude_cids,score_threshold}", templates)
        self.assertIn("qualcoder://search/regex{?pattern,flags,cursor,page_size,file_ids,exclude_cids,context_chars}", templates)

    def test_project_coders_resource_contains_visibility(self):
        req = {"jsonrpc": "2.0", "id": 20, "method": "resources/read", "params": {"uri": "qualcoder://project/coders"}}
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        payload = json.loads(res["result"]["contents"][0]["text"])
        self.assertEqual("default", payload["current_coder"])
        self.assertIn("default", payload["visible_coders"])
        self.assertIn("hidden_user", payload["hidden_coders"])

    def test_code_segments_diverse_by_document_strategy(self):
        req = {
            "jsonrpc": "2.0",
            "id": 22,
            "method": "resources/read",
            "params": {"uri": "qualcoder://codes/segments/1?strategy=diverse_by_document&max_segments=4&max_chars=1000"},
        }
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        payload = json.loads(res["result"]["contents"][0]["text"])
        ctid_order = [seg["ctid"] for seg in payload["segments"]]
        self.assertEqual([1, 2, 3, 4], ctid_order)
        self.assertEqual("visible", payload["selection"]["owner_scope"])
        self.assertTrue(payload["selection"]["visible_filter_applied"])
        self.assertIsNone(payload["selection"]["owner"])

    def test_code_segments_recent_first_strategy(self):
        req = {
            "jsonrpc": "2.0",
            "id": 23,
            "method": "resources/read",
            "params": {"uri": "qualcoder://codes/segments/1?strategy=recent_first&max_segments=4&max_chars=1000"},
        }
        res = self.server.handle_request(req)
        payload = json.loads(res["result"]["contents"][0]["text"])
        ctid_order = [seg["ctid"] for seg in payload["segments"]]
        self.assertEqual([4, 2, 3, 1], ctid_order)

    def test_code_segments_include_line_ranges(self):
        req = {
            "jsonrpc": "2.0",
            "id": 39,
            "method": "resources/read",
            "params": {"uri": "qualcoder://codes/segments/1?strategy=sequential&max_segments=10&max_chars=1000"},
        }
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        payload = json.loads(res["result"]["contents"][0]["text"])
        line_by_ctid = {seg["ctid"]: (seg["line_start"], seg["line_end"]) for seg in payload["segments"]}
        self.assertEqual((1, 1), line_by_ctid[2])
        self.assertEqual((2, 2), line_by_ctid[5])

    def test_code_segments_sequential_strategy(self):
        req = {
            "jsonrpc": "2.0",
            "id": 24,
            "method": "resources/read",
            "params": {"uri": "qualcoder://codes/segments/1?strategy=sequential&max_segments=3&max_chars=1000"},
        }
        res = self.server.handle_request(req)
        payload = json.loads(res["result"]["contents"][0]["text"])
        ctid_order = [seg["ctid"] for seg in payload["segments"]]
        self.assertEqual([1, 2, 3], ctid_order)

    def test_code_segments_char_budget_truncates_payload(self):
        req = {
            "jsonrpc": "2.0",
            "id": 25,
            "method": "resources/read",
            "params": {"uri": "qualcoder://codes/segments/1?strategy=sequential&max_segments=10&max_chars=6"},
        }
        res = self.server.handle_request(req)
        payload = json.loads(res["result"]["contents"][0]["text"])
        self.assertEqual(2, len(payload["segments"]))
        self.assertFalse(payload["segments"][0]["quote_truncated"])
        self.assertTrue(payload["segments"][1]["quote_truncated"])
        self.assertEqual(6, payload["selection"]["returned_chars"])
        self.assertTrue(payload["selection"]["truncated"])
        self.assertEqual(2, payload["selection"]["next_cursor"])

    def test_code_segments_owner_override_returns_hidden_coder(self):
        req = {
            "jsonrpc": "2.0",
            "id": 26,
            "method": "resources/read",
            "params": {"uri": "qualcoder://codes/segments/1?owner=hidden_user&strategy=sequential&max_segments=10&max_chars=1000"},
        }
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        payload = json.loads(res["result"]["contents"][0]["text"])
        self.assertEqual(1, len(payload["segments"]))
        self.assertEqual("hidden_user", payload["segments"][0]["owner"])
        self.assertEqual("owner_override", payload["selection"]["owner_scope"])
        self.assertFalse(payload["selection"]["visible_filter_applied"])
        self.assertEqual("hidden_user", payload["selection"]["owner"])

    def test_code_segments_owner_override_unknown_coder_returns_error(self):
        req = {
            "jsonrpc": "2.0",
            "id": 27,
            "method": "resources/read",
            "params": {"uri": "qualcoder://codes/segments/1?owner=does_not_exist"},
        }
        res = self.server.handle_request(req)
        self.assertIn("error", res)
        self.assertEqual(-32602, res["error"]["code"])

    def test_status_event_for_code_segments_contains_code_name(self):
        status = self.server.describe_status_event("resources/read", {"uri": "qualcoder://codes/segments/1"})
        self.assertTrue(isinstance(status, str))
        self.assertIn("code one", status)

    def test_resources_list_contains_only_top_level_resources(self):
        res = self.server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {}})
        self.assertIn("result", res)
        uris = [r["uri"] for r in res["result"]["resources"]]
        self.assertIn("qualcoder://project/memo", uris)
        self.assertIn("qualcoder://project/coders", uris)
        self.assertIn("qualcoder://codes/tree", uris)
        self.assertIn("qualcoder://documents", uris)
        self.assertIn("qualcoder://journals", uris)
        self.assertNotIn("qualcoder://documents/text/1", uris)
        self.assertNotIn("qualcoder://journals/1", uris)

    def test_resources_read_document_slice(self):
        req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "resources/read",
            "params": {"uri": "qualcoder://documents/text/1", "start": 2, "length": 4},
        }
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        payload = json.loads(res["result"]["contents"][0]["text"])
        self.assertEqual(1, payload["id"])
        self.assertEqual("cdef", payload["text"])
        self.assertEqual(2, payload["start"])
        self.assertEqual(1, payload["line_start"])
        self.assertEqual(1, payload["line_end"])

    def test_resources_read_document_by_line_range(self):
        req = {
            "jsonrpc": "2.0",
            "id": 36,
            "method": "resources/read",
            "params": {"uri": "qualcoder://documents/text/4", "line_start": 2, "line_end": 3},
        }
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        payload = json.loads(res["result"]["contents"][0]["text"])
        self.assertEqual(4, payload["id"])
        self.assertEqual("line2\nline3\n", payload["text"])
        self.assertEqual(6, payload["start"])
        self.assertEqual(12, payload["length"])
        self.assertEqual(2, payload["line_start"])
        self.assertEqual(3, payload["line_end"])

    def test_resources_read_document_rejects_mixed_char_and_line_windows(self):
        req = {
            "jsonrpc": "2.0",
            "id": 37,
            "method": "resources/read",
            "params": {"uri": "qualcoder://documents/text/4", "start": 0, "line_start": 1},
        }
        res = self.server.handle_request(req)
        self.assertIn("error", res)
        self.assertEqual(-32602, res["error"]["code"])

    def test_parse_vector_search_options_accepts_file_ids_and_exclude_cids(self):
        options = self.server._parse_vector_search_options(
            {
                "q": ["work"],
                "file_ids": ["1,2"],
                "exclude_cids": ["4,5"],
            }
        )
        self.assertEqual([1, 2], options["file_ids"])
        self.assertEqual([4, 5], options["exclude_cids"])
        self.assertNotIn("page_size", options)
        self.assertNotIn("k_per_query", options)

    def test_parse_vector_search_options_ignores_removed_tuning_parameters(self):
        options = self.server._parse_vector_search_options(
            {
                "q": ["work"],
                "page_size": ["50"],
                "k_per_query": ["100"],
            }
        )
        self.assertEqual(["work"], options["queries"])
        self.assertNotIn("page_size", options)
        self.assertNotIn("k_per_query", options)

    def test_parse_regex_search_options_accepts_file_ids_and_exclude_cids(self):
        options = self.server._parse_regex_search_options(
            {
                "pattern": ["abc"],
                "file_ids": ["1,2"],
                "exclude_cids": ["7,8"],
            }
        )
        self.assertEqual([1, 2], options["file_ids"])
        self.assertEqual([7, 8], options["exclude_cids"])

    def test_regex_search_with_file_ids_filters_to_selected_documents(self):
        req = {
            "jsonrpc": "2.0",
            "id": 34,
            "method": "resources/read",
            "params": {"uri": "qualcoder://search/regex?pattern=.&file_ids=1&context_chars=0&page_size=50"},
        }
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        payload = json.loads(res["result"]["contents"][0]["text"])
        self.assertEqual([1], payload["selection"]["file_ids"])
        self.assertTrue(len(payload["hits"]) > 0)
        self.assertTrue(all(hit["source_id"] == 1 for hit in payload["hits"]))
        self.assertTrue(all("line_start" in hit and "line_end" in hit for hit in payload["hits"]))

    def test_regex_search_exclude_cids_returns_only_new_passages(self):
        req = {
            "jsonrpc": "2.0",
            "id": 35,
            "method": "resources/read",
            "params": {
                "uri": "qualcoder://search/regex?pattern=.&file_ids=1&exclude_cids=1&context_chars=0&page_size=50"
            },
        }
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        payload = json.loads(res["result"]["contents"][0]["text"])
        self.assertEqual([1], payload["selection"]["exclude_cids"])
        self.assertEqual(1, len(payload["hits"]))
        self.assertEqual(1, payload["hits"][0]["source_id"])
        self.assertEqual(5, payload["hits"][0]["match_start"])
        self.assertEqual(1, payload["hits"][0]["line_start"])
        self.assertEqual(1, payload["hits"][0]["line_end"])

    def test_regex_search_returns_line_ranges_for_multiline_context(self):
        req = {
            "jsonrpc": "2.0",
            "id": 38,
            "method": "resources/read",
            "params": {"uri": "qualcoder://search/regex?pattern=line3&file_ids=4&context_chars=0&page_size=10"},
        }
        res = self.server.handle_request(req)
        self.assertIn("result", res)
        payload = json.loads(res["result"]["contents"][0]["text"])
        self.assertEqual(1, len(payload["hits"]))
        self.assertEqual(3, payload["hits"][0]["line_start"])
        self.assertEqual(3, payload["hits"][0]["line_end"])

    def test_unknown_method_returns_jsonrpc_error(self):
        res = self.server.handle_request({"jsonrpc": "2.0", "id": 4, "method": "unknown/method", "params": {}})
        self.assertIn("error", res)
        self.assertEqual(-32601, res["error"]["code"])

    def test_status_event_for_document_read_contains_id_and_name(self):
        status = self.server.describe_status_event("resources/read", {"uri": "qualcoder://documents/text/1"})
        self.assertTrue(isinstance(status, str))
        self.assertIn("doc one", status)

    def test_status_text_for_document_read_uses_document_name(self):
        status = self.server.describe_status_event("resources/read", {"uri": "qualcoder://documents/text/1"})
        self.assertIn("doc one", status)

    def test_status_event_for_documents_list(self):
        status = self.server.describe_status_event("resources/read", {"uri": "qualcoder://documents"})
        self.assertTrue(isinstance(status, str))
        self.assertTrue(len(status) > 0)

    def test_status_event_for_project_coders(self):
        status = self.server.describe_status_event("resources/read", {"uri": "qualcoder://project/coders"})
        self.assertTrue(isinstance(status, str))
        self.assertTrue(len(status) > 0)

    def test_status_event_for_create_category_contains_category_name(self):
        status = self.server.describe_status_event(
            "tools/call",
            {"name": "codes/create_category", "arguments": {"name": "My Category"}},
        )
        self.assertIn("My Category", status)

    def test_status_event_for_create_code_contains_code_name(self):
        status = self.server.describe_status_event(
            "tools/call",
            {"name": "codes/create_code", "arguments": {"name": "My Code"}},
        )
        self.assertIn("My Code", status)

    def test_status_event_for_create_text_coding_contains_code_and_document_name(self):
        status = self.server.describe_status_event(
            "tools/call",
            {"name": "codes/create_text_coding", "arguments": {"cid": 1, "fid": 1, "quote": "abc"}},
        )
        self.assertIn("code one", status)
        self.assertIn("doc one", status)
