import time
import re
import json
import argparse
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

base_dir = Path(__file__).resolve().parent
allowed_symbols = r"`~!@#$%^&*()_\-+=\[\]{}\\|;:'\",.<>/?"
pattern = rf"[^\u0041-\u005A\u0061-\u007A\u00C0-\u024F\uAC00-\uD7A30-9{allowed_symbols}\s]"
forbidden_regex = re.compile(pattern)

class Track:
    def __init__(self, id, title, artist, year=None, yt_link=None):
        self.id = id
        self.title = title
        self.artist = artist
        self.year = year
        self.yt_link = yt_link

    def __str__(self):
        return f"{self.id}\t{self.title}\t{self.artist}\t{self.year}"
    
class Artist:
    def __init__(self, name, gender):
        self.name = name

    def __str__(self):
        return f"{self.name}"

class Crawler:
    def __init__(self):
        self.tracks = []
        self.track_id_set = set()
        self.artists = {}

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")

        self.driver = webdriver.Chrome(options=options)

    def load_crawled_entries(self, raw=False):
        data_file = base_dir.parent / "tracks/melon.json"

        with open(data_file, "r", encoding="utf-8") as f:
            json_data = json.load(f)

            for track_data in json_data:
                self.tracks.append(Track(track_data["id"], track_data["title"], track_data["artist"], year=track_data["year"], yt_link=track_data["yt_link"]))
                self.track_id_set.add(track_data["id"])

    def print_crawled_entries(self):
        for track in self.tracks:
            if track.id < 10000:
                print(track)

    def save_crawled_raw_entries(self, batch):
        data_file = base_dir.parent / f"tracks/raw{batch}.json"

        elems = []

        for track in self.tracks:
            elems.append(track.__dict__)

        with open(data_file, "w", encoding="utf-8") as f:
            json.dump(elems, f, indent=2, ensure_ascii=False)

        self.tracks = []

    def save_crawled_entries(self):
        data_file = base_dir.parent / f"tracks/melon.json"
        elems = []
        for track in self.tracks:
            elems.append(track.__dict__)

        
        with open(data_file, "w", encoding="utf-8") as f:
            json.dump(elems, f, indent=2, ensure_ascii=False)


    def collect_artists(self):
        for track in self.tracks:
            artist_rm = []
            depth = 0

            for c in track.artist:
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                
                if depth == 0 and c != ')':
                    artist_rm.append(c)
            
            artist_str = "".join(artist_rm)

            self.artists[artist_str] = Artist(artist_str, None)

    def show_artists(self):
        self.collect_artists()

        print(f"Artists: {len(self.artists)}")

        for artist in self.artists.values():
            print(artist)

    def has_forbidden_char(self, s):
        return bool(forbidden_regex.search(s))
    
    def query_melon_by_year(self, year):
        query_url_string = f"https://www.melon.com/chart/age/index.htm?chartType=YE&chartGenre=KPOP&chartDate={year}"
        self.driver.get(query_url_string)

        res = self.driver.page_source

        soup = BeautifulSoup(res, "html.parser")

        rows50 = soup.find_all("tr", class_="lst50")
        rows100 = soup.find_all("tr", class_="lst100")

        for row in rows50 + rows100:
            div_title = row.find("div", class_="rank01")

            if div_title is None:
                continue
            
            finder = div_title.find("a")

            if finder is None:
                continue

            title = finder.text.rstrip()

            div_artist = row.find("div", class_="rank02")
            artist = div_artist.find("span", class_="checkEllipsis").text.rstrip()

            id_str = f"{title}||{artist}"
            
            if id_str not in self.track_id_set:
                self.track_id_set.add(id_str)
                self.tracks.append(Track(id_str, title, artist))

    def query_melon_on_top100(self):
        pass

    def filter_tracks(self):
        filtered = []

        for track in self.tracks:
            if not self.has_forbidden_char(track.title) and not self.has_forbidden_char(track.artist):
                filtered.append(track)

        self.tracks = filtered


    def query_melon(self):
        for year in range(2010, 2025):
            self.query_melon_by_year(year)

    def query_youtube_link(self, track):
        search_keyword = f"{track.title} {track.artist} 가사"
        search_keyword = search_keyword.replace(" ", "+")
        query_url = f"https://www.youtube.com/results?search_query={search_keyword}"

        self.driver.get(query_url)
        res = self.driver.page_source
        soup = BeautifulSoup(res, "html.parser")


    def fetch_youtube_links(self):
        self.query_youtube_link(self.tracks[0])


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-a', '--artist', action="store_true", help="the target file to symbolically execute")
    arg_parser.add_argument('-t', "--track", action="store_true")
    arg_parser.add_argument('-r', "--raw", action="store_true")
    arg_parser.add_argument('-c', "--crawl", action="store_true")
    arg_parser.add_argument('-y', "--youtube", action="store_true")
    args = arg_parser.parse_args()


    crawler = Crawler()
    
    if args.crawl:
        crawler.query_melon()
        crawler.save_crawled_entries()
    elif args.youtube:
        crawler.load_crawled_entries()
        crawler.fetch_youtube_links()
        
    elif args.raw:
        if args.artist:
            crawler.load_crawled_entries(raw=True)
            crawler.show_artists()

    else:
        if args.artist:
            crawler.load_crawled_entries(raw=False)
            crawler.show_artists()