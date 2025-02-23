#!/usr/bin/env python3
"""Usage: stream-index.py [options]

Generates the stream index table for Joepedia from a spreadsheet.

Options:
    -h --help            Display this help.
    -i --input IN        The path to a CSV file to read the spreadsheet data
                         from, if downloading the data this will be written
                         to with the new data. [default: Joe - Streams.csv]
    -o --output OUT|-    The file to write to with the output wikitext.
                         [default: stream-index.txt]
    --overwrite-output   Allow overwriting the output wiki file.
    -d --download        Try to download the latest data from the spreadsheet,
                         requires a google API key from the GOOGLE_API_KEY
                         environment variable and the googleapiclient library
                         installed.
    --overwrite-input    Allow overwriting the input CSV file if downloading.

Uncommon Options:
    --spreadsheet-id ID  Specify the ID of the google spreadsheet to source the
                         data from, when downloading.
                         [default: 1ITQm2xYrVj7sycFsjwPSe8bbCFu3OJmPSGtzm3ZImRE]
    --skip-rows NUM      The number of rows to skip from the spreadsheet, to
                         ignore headers.
                         [default: 7]
    --colors FILE        The JSON file to load a list of colors from.
                         [default: colors.json]
    --replacements FILE  The JSON file to load a list of text replacements from.
                         [default: replacements.json]
    --additional FILE    The JSON file to load a list of additional stream data
                         from. [default: additional_stream_data.json]

"""

import csv
import itertools
import json
import os
import random
import sys
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from datetime import datetime

from docopt import docopt

# Where this script can be found.
SCRIPT = "https://github.com/jads-dev/joepedia-stream-index"

# A warning added to the output to discourage manual edits.
WARNING = [
    "<!--",
    "  This content is generated by a script which can be found at ",
    f"  {SCRIPT}.",
    "  Manual changes **WILL BE LOST** when the script is next run, you almost",
    "  certainly want to re-run the script with new data, make changes to the ",
    "  script, or modify the StreamIndexEntry template instead.",
    "-->",
]


def wikify_link(key, link):
    if not link:
        return {}
    link_with_protocol = link if link.startswith("https://") else f"https://{link}"
    sanitised_link = link_with_protocol.replace("=", "&#61;")
    return {key: f"{sanitised_link}"}


def canonicalise(replacements, value):
    for target, replacement in replacements.items():
        value = value.replace(target, replacement)
    return value


def obtain(file_id, api_key):
    from googleapiclient.discovery import build

    with build("drive", "v3", developerKey=api_key) as drive:
        data = drive.files().export(fileId=file_id, mimeType="text/csv").execute()
        if not data:
            raise Exception("Could not obtain spreadsheet data.")
        else:
            return data.decode("utf-8")


def read_and_standardise(file, skip_rows, replacements, additional_stream_data):
    reader = csv.reader(file, delimiter=",")
    previous_index, previous_date = None, None
    part = 1
    for row in itertools.islice(reader, skip_rows + 1, None):
        [
            index,
            date,
            other_date,
            game,
            game_index,
            vod_with_chat,
            _,
            _,
            vod_without_chat,
            *_,
        ] = row

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

        additional = additional_stream_data.get(current_index, {})

        yield {
            "index": current_index,
            "date": datetime.strptime(current_date, "%a, %m/%d/%Y").strftime(
                "%Y-%m-%d"
            ),
            "part": part,
            "game": canonicalise(replacements, game),
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


def generate_wiki_source(
    data_source_id,
    rows,
    colors,
):
    data_source_url = f"https://docs.google.com/spreadsheets/d/{data_source_id}"
    data_attribution = f"sourced from a spreadsheet maintained {{{{Attribution|Falco}}}}<ref>[{data_source_url} Falco’s Spreadsheet of Joe content].</ref>"
    script_attribution = f"and processed using a script originally written {{{{Attribution|JayUplink}}}}<ref>[{SCRIPT} “joepedia-stream-index” on GitHub].</ref>"
    attributions = ", ".join([data_attribution, script_attribution])

    multipart = {row["index"] for row in rows if row["part"] > 1}

    games = {row["game"]: random.choice(colors) for row in rows}

    yield from WARNING
    yield """<div style="display: flex; justify-content: center;">"""
    yield """{| class="wikitable" """
    yield f"""  |+ style="caption-side:bottom;"|This data is {attributions}."""
    yield "|-"
    yield "! # !! Date !! Game !! No. in Series !! Available VODs"
    yield ""

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
        arguments = "|".join(
            itertools.chain.from_iterable(
                as_template_argument(key, value)
                for (key, value) in template_args.items()
                if value
            )
        )
        yield f"  {{{{StreamIndexEntry|{arguments}}}}}"
        previous_index = index

    yield "|}"
    yield "</div>"
    yield from WARNING
    yield ""


@contextmanager
def open_overwrite(file, arguments, overwrite_arg_name):
    try:
        yield open(file, "w" if arguments[overwrite_arg_name] else "x")
    except FileExistsError:
        print(
            f"Error: The file “{file}” already exists, use the “{overwrite_arg_name}” argument if you wish to overwrite it.",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    arguments = docopt(__doc__)

    download = arguments["--download"]
    input_file = arguments["--input"]
    data_source_id = arguments["--spreadsheet-id"]
    output_file = arguments["--output"]

    with open(arguments["--replacements"], "r") as file:
        replacements = json.load(file)

    with open(arguments["--colors"], "r") as file:
        colors = json.load(file)

    with open(arguments["--additional"], "r") as file:
        additional_stream_data = {
            int(key): value for (key, value) in json.load(file).items()
        }

    if download:
        api_key = os.environ.get("GOOGLE_API_KEY", None)
        data = obtain(data_source_id, api_key)
        with open_overwrite(input_file, arguments, "--overwrite-input") as file:
            file.write(data)

    with open(input_file, "r") as file:
        rows = list(
            read_and_standardise(
                file,
                int(arguments["--skip-rows"], base=10),
                replacements,
                additional_stream_data,
            )
        )

    wikitext = generate_wiki_source(data_source_id, rows, colors)

    if output_file == "-":
        for line in wikitext:
            print(line)
    else:
        with open_overwrite(output_file, arguments, "--overwrite-output") as file:
            file.writelines(f"{line}\n" for line in wikitext)
