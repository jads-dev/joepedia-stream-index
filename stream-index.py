import csv
import sys
import itertools
from datetime import datetime
import random
from collections.abc import Iterable, Mapping

# The number of rows in the spreadsheet we expect to be header rows that should be skipped.
NUMBER_OF_HEADER_ROWS = 7

# Replacements used to make the title canonical.
REPLACEMENTS = {
    "Jedi: Fallen Order": "Star Wars Jedi: Fallen Order",
    "Jedi: Survivor": "Star Wars Jedi: Survivor",
    "\"Don't Starve\"": "Don't Starve",
    "Life is Strange: Bore the Storm": "Life is Strange: Before the Storm",
    "Dr. Langeskov, The Tiger, and The Terribly Cursed Emerald: A Whirlwind Heist": "Dr. Langeskov",
    "Unrendered": "",
    "Joe...": "",
    "Slay The Princess": "Slay the Princess",
    "Umineko When They Cry": "Umineko When They Cry - Question Arcs",
    "NieR:Automata": "NieR: Automata",
    "Doki Doki Literature Club!": "Doki Doki Literature Club",
    "Outer Wilds DLC": "Outer Wilds: Echoes of the Eye",
    "Control Alan Wake DLC": "Control: AWE",
    "13 Sentinels": "13 Sentinels: Aegis Rim",
}

COLOURS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
           "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]

ADDITIONAL_INFO = {
    787: {"guest": ["Greg Chun"]},
    797: {"guest": ["Mouse"]},
}


def wikify_link(key, link):
    if not link:
        return {}
    link_with_protocol = link if link.startswith(
        "https://") else f"https://{link}"
    sanitised_link = link_with_protocol.replace("=", "&#61;")
    return {key: f"{sanitised_link}"}


def canonicalise(value):
    for (target, replacement) in REPLACEMENTS.items():
        value = value.replace(target, replacement)
    return value


def read_from(file):
    reader = csv.reader(file, delimiter=",")
    previous_index, previous_date = None, None
    part = 1
    for row in itertools.islice(reader, NUMBER_OF_HEADER_ROWS + 1, None):
        [index, date, other_date, game, game_index, vod_with_chat,
            _, _, vod_without_chat, *_] = row

        # Skip graph at the end.
        if (not index and date) or other_date == "(Today)":
            continue

        vods = {
            **wikify_link("with_chat", vod_with_chat),
            **wikify_link("without_chat", vod_without_chat),
        }

        current_index = int(index) if index else previous_index
        current_date = date if date else previous_date
        part = part + 1 if not index else 1

        # Skip joke Signalis entries.
        if current_index < 300 and game == "Signalis":
            continue

        additional = ADDITIONAL_INFO.get(current_index, {})

        yield {
            "index": current_index,
            "date": datetime.strptime(current_date, "%a, %m/%d/%Y").strftime("%Y-%m-%d"),
            "part": part,
            "game": canonicalise(game),
            "game_index": game_index,
            "vod": vods,
            **additional,
        }

        previous_index, previous_date = current_index, current_date


def as_template_argument(key, value):
    if isinstance(value, Mapping):
        for subkey, subvalue in value.items():
            yield f"{key}_{subkey}={subvalue}"
    elif not isinstance(value, str) and isinstance(value, Iterable):
        for index, subvalue in enumerate(value):
            index_str = f"{index + 1}" if index > 0 else ""
            yield f"{key}{index_str}={subvalue}"
    else:
        yield f"{key}={value}"


if __name__ == "__main__":
    with open(sys.argv[1] if len(sys.argv) > 1 else "Joe - Streams.csv", "r") as file:
        print(
            """{| class="wikitable"\n  |-\n  ! # !! Date !! Game !! No. in Series !! Available VODs"""
        )

        rows = list(read_from(file))

        multipart = {row["index"]
                     for row in rows if row["part"] > 1}

        games = {row["game"]: random.choice(COLOURS) for row in rows}

        previous_index = None
        for row in reversed(rows):
            index = row["index"]
            template_args = {
                **row,
                "color": games[row["game"]],
            }
            # Only include the part if it's not a single game stream.
            if index not in multipart:
                del template_args["part"]
            else:
                if not previous_index == index:
                    template_args["last_part"] = 1
            arguments = "|".join(itertools.chain.from_iterable(as_template_argument(key, value)
                                 for (key, value) in template_args.items() if value))
            print(
                f"  {{{{StreamIndexEntry|{arguments}}}}}"
            )
            previous_index = index

        print("|}")
