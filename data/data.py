import time
import re
import json
import argparse
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

base_dir = Path(__file__).resolve().parent
song_path = base_dir / "songs.json"

YDL_OPTIONS = {'format': 'bestaudio', 'outtmpl': 'songs/%(id)s.opus'}



class Track:
    def __init__(self, id: int, title: str, artist: str, yt_uri: str | None = None, yt_vid_title: str | None = None):
        self.id = id
        self.title = title
        self.artist = artist
        self.yt_uri = yt_uri
        self.yt_vid_title = yt_vid_title

    def __str__(self):
        return f"{self.id}\t{self.title}\t{self.artist}\t{self.yt_uri}"
    
class Artist:
    def __init__(self, name, gender):
        self.name = name

    def __str__(self):
        return f"{self.name}"

class SongManager:
    def __init__(self):
        self.tracks = []
        self.track_dist_set = set()
        self.artists = {}
        self.track_new_id = 0

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")

        self.driver = webdriver.Chrome(options=options)

    def dist_str(title: str, artist: str):
        return f"{title}|{artist}"

    def load_crawled_entries(self):
        with open(song_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)

            for track_data in json_data:
                yt_uri = None
                if "yt_uri" in track_data:
                    yt_uri = track_data["yt_uri"]

                track = Track(track_data["id"], track_data["title"], track_data["artist"], yt_uri=yt_uri)
                self.tracks.append(track)
                dist_str = SongManager.dist_str(track.title, track.artist)
                self.track_dist_set.add(dist_str)


    def save_crawled_entries(self):
        elems = []
        for track in self.tracks:
            elems.append(track.__dict__)

        with open(song_path, "w", encoding="utf-8") as f:
            json.dump(elems, f, indent=2, ensure_ascii=False)

    def query_melon_by_year(self, year: int):
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

            dist_str = SongManager.dist_str()
            
            if dist_str not in self.track_dist_set:
                new_id = self.track_new_id
                self.track_new_id += 1
                self.track_dist_set.add(dist_str)
                self.tracks.append(Track(new_id, title, artist))

    def query_melon_on_top100(self):
        #TODO
        pass

    def query_melon(self):
        for year in range(2010, 2025):
            self.query_melon_by_year(year)
        
        self.query_melon_on_top100()

    def query_youtube_link(self, track: Track):
        search_keyword = f"{track.title} {track.artist} 가사"
        search_keyword = search_keyword.replace(" ", "+")
        query_url = f"https://www.youtube.com/results?search_query={search_keyword}"

        self.driver.get(query_url)
        time.sleep(3)
        res = self.driver.page_source
        soup = BeautifulSoup(res, "html.parser")

        list_container = soup.find("ytd-two-column-search-results-renderer", class_="ytd-search")
        vids = list_container.find_all("ytd-video-renderer", class_="ytd-item-section-renderer")

        with open("listdiv.html", "w", encoding="utf-8") as f:
            f.write(vids[0].prettify())

        # TODO: Get YT links. This work would be done sequentially.
        # TODO: Also, get YT video title for future use.

    def fetch_youtube_links(self):
        self.query_youtube_link(self.tracks[-2])

    def download_youtube_audios(self):
        # TODO
        pass

    def process_add_requests(self):
        # TODO
        pass

    def process_update_requests(self):
        # TODO
        pass

    def process_remove_requests(self):
        # TODO
        pass

if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-m', "--melon", action="store_true", help="query melon chart to collect basic database of songs.")
    arg_parser.add_argument('-y', "--youtube", action="store_true", help="find YT links, and downloads YT audio.")
    arg_parser.add_argument('-a', "--add", action="store_true", help="add new songs based on 'add_requests.json'")
    arg_parser.add_argument('-u', "--update", action="store_true", help="update existing songs based on 'update_requests.json'")
    arg_parser.add_argument('-r', "--remove", action="store_true", help="remove existing songs based on 'remove_requests.json'")
    args = arg_parser.parse_args()


    manager = SongManager()
    
    if args.melon:
        manager.load_crawled_entries()
        manager.query_melon()

    elif args.youtube:
        manager.load_crawled_entries()
        manager.fetch_youtube_links()
        manager.download_youtube_audios()
    
    elif args.add:
        manager.process_add_requests()

    elif args.update:
        manager.process_update_requests()
        
    elif args.remove:
        manager.process_remove_requests()

    else:
        print("Usage: data.py [OPTIONS]")