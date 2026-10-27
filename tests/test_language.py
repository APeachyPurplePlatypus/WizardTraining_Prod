import unittest

from wizardtraining.language import LanguageFiles, parse_lang_file, split_code

LINE_BREAK = "\r\n"


def lang_file(name: str, entries: dict) -> bytes:
    lines = [f"0:{name}"]
    for key, text in entries.items():
        lines += [key, "", text]
    return LINE_BREAK.join(lines).encode("utf-16")


class LanguageTest(unittest.IsolatedAsyncioTestCase):
    def test_split_code(self):
        self.assertEqual(split_code("QuestTitle_1625D8"), ("QuestTitle", "1625D8"))
        self.assertEqual(split_code("WC-NPCs_00001718"), ("WC-NPCs", "00001718"))
        self.assertIsNone(split_code("Quest Finder"))

    def test_parse_lang_file(self):
        self.assertEqual(parse_lang_file(lang_file("QuestTitle", {"1625D8": "A Title", "1625C2": "Another"})),
                         {"1625D8": "A Title", "1625C2": "Another"})
        self.assertEqual(parse_lang_file(b"\xff"), {})

    async def test_looks_codes_up_reading_each_file_once(self):
        reads = []

        async def read_file(path):
            reads.append(path)
            return lang_file("QuestTitle", {"1625D8": "A Title"})

        language = LanguageFiles(read_file)
        self.assertEqual(await language.text("QuestTitle_1625D8"), "A Title")
        self.assertIsNone(await language.text("QuestTitle_FFFFFF"))
        self.assertIsNone(await language.text("Quest Finder"))
        self.assertEqual(reads, ["Locale/en-US/QuestTitle.lang"])

    async def test_a_missing_file_gives_no_text(self):
        async def read_file(path):
            raise FileNotFoundError(path)

        self.assertIsNone(await LanguageFiles(read_file).text("Nope_1"))


if __name__ == "__main__":
    unittest.main()
