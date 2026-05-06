import unittest

from lynx_memory.transcript import find_last_turn_codex


class CodexTranscriptTest(unittest.TestCase):
    def test_codex_turn_keeps_apply_patch_content_with_assistant_text(self):
        msgs = [
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "fix the cell"}],
                },
            },
            {"type": "event_msg", "payload": {"turn_id": "turn-1"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "I will patch it."}],
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "apply_patch",
                    "input": (
                        "*** Begin Patch\n"
                        "*** Update File: VideoContentCollectionViewCell.swift\n"
                        "@@\n"
                        "-    guard let videoPlayerView, videoPlayerView.superview != containerView else { return }\n"
                        "+    guard let videoPlayerView else { return }\n"
                        "*** End Patch"
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Patched."}],
                },
            },
        ]

        user_text, user_uuid, asst_text, asst_uuid, had_prose = find_last_turn_codex(msgs)

        self.assertEqual(user_text, "fix the cell")
        self.assertEqual(user_uuid, "turn-1:user")
        self.assertEqual(asst_uuid, "turn-1:assistant")
        self.assertTrue(had_prose)
        self.assertIn("I will patch it.", asst_text)
        self.assertIn("**Tool: apply_patch**", asst_text)
        self.assertIn("```diff", asst_text)
        self.assertIn("*** Update File: VideoContentCollectionViewCell.swift", asst_text)
        self.assertIn("+    guard let videoPlayerView else { return }", asst_text)
        self.assertTrue(asst_text.rstrip().endswith("```"))
        self.assertIn("Patched.", asst_text)


if __name__ == "__main__":
    unittest.main()
