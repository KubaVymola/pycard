from jinja2 import Template, Environment, FileSystemLoader
import os
from optparse import OptionParser
import logging
import csv
import time
import re
import math
from watchdog.observers import Observer
from watchdog.events import LoggingEventHandler, FileSystemEventHandler
from itertools import zip_longest
from livereload import Server
import json


VERSION = '0.2.0'

RENDERED_CARDS_FILE = "index.html"
PAGE_HEIGHT_MM = 277
PAGE_WIDTH_MM = 190
# PAGE_HEIGHT_MM = 227
# PAGE_WIDTH_MM = 160

class CardRenderer:
    def __init__(self, input_path, common_path, prefix):
        self.prefix = prefix
        self.input_path = input_path
        self.common_path = common_path

        self.csv_card_path = self.get_prefixed_path("json")
        self.custom_header_path = self.get_prefixed_path("header.html")
        self.single_card_front_path = self.get_prefixed_path("html")
        self.single_card_back_path = self.get_prefixed_path("back.html")

        self.config_path = os.path.join(self.input_path, "config.ini")

        self.cards_template_path = os.path.join(os.path.dirname(__file__), 'cards.html')

        self.all_cards_rendered_path = os.path.join(input_path, RENDERED_CARDS_FILE)

    def get_prefixed_path(self, extension):
        return os.path.join(self.input_path, "{}.{}".format(self.prefix, extension))

    def render_cards(self):
        # I've noticed that when saving the CSV file
        # the server reloads an empty page
        # unless I add a small sleep before attempting to read everything
        time.sleep(0.5)

        config = { "rows": 5, "cols": 5}

        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                for line in f:
                    [key, value] = line.split('=')

                    if key == 'ROWS': config["rows"] = int(value)
                    if key == 'COLS': config["cols"] = int(value)

        cards_per_page = config["rows"] * config["cols"]
        card_height = round(PAGE_HEIGHT_MM / config["rows"], 2)
        card_width = round(PAGE_WIDTH_MM / config["cols"], 2)

        # load the csv file

        
        f = open(self.csv_card_path)
        cards_data = json.load(f)

        for card_data in cards_data:
            print(card_data)
        
        # cards_data = []
        # with open(self.csv_card_path, "r", encoding='utf-8-sig') as csvfile:
        #     reader = csv.DictReader(csvfile, dialect='custom_delimiter')
        #     for row in reader:
        #         cards_data.append(row)

        front_cards = []
        back_cards = []

        print(os.path.join(os.path.dirname(__file__), self.input_path, self.common_path))

        # load the single card template
        with open(self.single_card_front_path, "r") as front_file:
            # front_template = Template(front_file.read())
            front_template = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), self.input_path, self.common_path))).from_string(front_file.read())
            back_template = None

            if os.path.exists(self.single_card_back_path):
                with open(self.single_card_back_path) as back_file:
                    back_template = Template(back_file.read())

            for card_data in cards_data:
                if str(card_data.get('ignore', "false")).lower() == "true":
                    continue

                front_rendered = front_template.render(
                    card_data,
                    __card_data=card_data,
                    __time=str(time.time())
                )
                num_cards = card_data.get('num_cards')
                if num_cards is None:
                    num_cards = 1

                num_cards = int(num_cards)

                back_rendered = None
                if back_template is not None:
                    back_rendered = back_template.render(
                        card_data,
                        __card_data=card_data,
                        __time=str(time.time())
                    )

                for _ in range(num_cards):
                    front_cards.append(front_rendered)
                    back_cards.append(back_rendered)

        rendered_cards = []
        for i in range(0, len(front_cards), cards_per_page):
            rendered_cards.append({ "type": "front", "cards": front_cards[i:min(i + cards_per_page, len(front_cards))]})

            if back_template is not None:
                rendered_cards.append({ "type": "back", "cards": back_cards[i:min(i + cards_per_page, len(back_cards))]})

        # print(rendered_cards)

        # Load custom header html if it exists
        custom_header = None

        if os.path.exists(self.custom_header_path):
            with open(self.custom_header_path, "r") as f:
                custom_header = f.read()

        # render the cards template with all rendered cards
        with open(self.cards_template_path, "r") as cards_template_file:
            template = Template(cards_template_file.read())
            with open(self.all_cards_rendered_path, "w") as all_cards_rendered_file:
                all_cards_rendered_file.write(
                    template.render(
                        rendered_cards=rendered_cards,
                        prefix=self.prefix,
                        custom_header=custom_header,
                        card_height=str(card_height),
                        card_width=str(card_width),
                        page_height=PAGE_HEIGHT_MM,
                        cols=config["cols"],
                        rows=config["rows"]
                    )
                )


class RenderingEventHandler(FileSystemEventHandler):
    def __init__(self, card_renderer):
        self.card_renderer = card_renderer

    def on_any_event(self, event):
        # if event.src_path == self.card_renderer.all_cards_rendered_path:
        if event.src_path.endswith(self.card_renderer.all_cards_rendered_path):
            return

        self.card_renderer.render_cards()


def parse_options():
    parser = OptionParser(
        usage="usage: %prog [options]",
        version="%prog {}".format(VERSION)
    )
    parser.add_option("-p", "--path",
                      help="path to assets",
                      dest="path",
                      default=os.getcwd(),
                      metavar="PATH")

    parser.add_option("--common",
                      help="relative path from assets to common files",
                      dest="common",
                      default="..",
                      metavar="COMMON")

    parser.add_option("-x", "--prefix",
                      help="filename prefix, example _card<.ext>",
                      dest="prefix",
                      default="_card",
                      metavar="PREFIX")

    parser.add_option("-d", "--delimiter",
                      help="delimiter used in the csv file, default: , (comma)",
                      dest="delimiter",
                      default=",",
                      metavar="DELIMITER")

    parser.add_option("--port",
                      help="port to use for live reloaded page",
                      dest="port",
                      type="int",
                      default=8800,
                      metavar="PORT")

    parser.add_option("--address",
                      help="host address to bind to",
                      dest="host_address",
                      default="0.0.0.0",
                      metavar="ADDRESS")

    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')

    (options, args) = parse_options()

    port = options.port
    assets_path = options.path
    common_path = options.common
    file_prefix = options.prefix
    host_address = options.host_address

    csv.register_dialect('custom_delimiter', delimiter=options.delimiter)

    card_renderer = CardRenderer(assets_path, common_path, file_prefix)

    observer = Observer()
    observer.schedule(LoggingEventHandler(), assets_path, recursive=True)
    observer.schedule(RenderingEventHandler(card_renderer), assets_path, recursive=True)

    card_renderer.render_cards()

    observer.start()

    server = Server()
    server.watch(card_renderer.all_cards_rendered_path)
    server.serve(root=assets_path, port=port, host=host_address)

    observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
