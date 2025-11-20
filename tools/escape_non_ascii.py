import codecs
import sys
from pathlib import Path


def escape_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    out = ""
    for c in text:
        if ord(c) > 127:
            out += codecs.encode(c, "unicode_escape").decode(encoding="utf-8")
        else:
            out += c

    path.write_text(out, encoding="utf-8")


def main() -> None:
    for file in sys.argv[1:]:
        escape_file(Path(file))


if __name__ == "__main__":
    main()
