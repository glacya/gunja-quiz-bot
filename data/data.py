import time
import json
import re
import argparse
import os
import yt_dlp
import subprocess
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from concurrent.futures import ThreadPoolExecutor, as_completed

base_dir = Path(__file__).resolve().parent
song_path = base_dir / "songs.json"
exclude_path = base_dir / "forbidden.json"
allowed_symbols = r"`~!@#$%^&*()_\-+=\[\]{}\\|;:'\",.<>/?’"
pattern = rf"[^\u0041-\u005A\u0061-\u007A\u00C0-\u024F\uAC00-\uD7A30-9{allowed_symbols}\s]"
forbidden_regex = re.compile(pattern)

YDL_OPTIONS = {'format': 'bestaudio', 'outtmpl': 'songs/%(id)s.opus', 'quiet': True}

class Track:
    def __init__(self, id: int, title: str, artist: str, yt_uri: str | None = None, yt_vid_title: str | None = None, yt_vid_length: int | None = None, upvotes: int = 0, downvotes: int = 0):
        self.id = id
        self.title = title
        self.artist = artist
        self.yt_uri = yt_uri
        self.yt_vid_title = yt_vid_title
        self.yt_vid_length = yt_vid_length
        self.upvotes = upvotes
        self.downvotes = downvotes

    def __str__(self):
        return f"{self.id}\t{self.title}\t{self.artist}\t{self.yt_uri}"

class SongManager:
    def __init__(self):
        self.tracks = []
        self.track_dist_set = set()
        self.track_new_id = 0
        self.artists = set()

    def run_webdriver(self):
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")

        self.driver = webdriver.Chrome(options=options)

    # Creates a unique string of a track, by concatenating title and artist.
    def dist_str(title: str, artist: str):
        return f"{title}|{artist}"

    def load_crawled_entries(self):
        try:
            f = open(song_path, "r", encoding="utf-8")
            json_data = json.load(f)

            for track_data in json_data:
                yt_uri = None
                yt_vid_length = None
                yt_vid_title = None
                if "yt_uri" in track_data:
                    yt_uri = track_data["yt_uri"]
                    yt_vid_length = track_data["yt_vid_length"]
                    yt_vid_title = track_data["yt_vid_title"]

                track = Track(track_data["id"], track_data["title"], track_data["artist"], yt_uri=yt_uri, yt_vid_length=yt_vid_length, yt_vid_title=yt_vid_title)
                self.tracks.append(track)
                dist_str = SongManager.dist_str(track.title, track.artist)
                self.track_dist_set.add(dist_str)
                self.artists.add(track.artist)
                self.track_new_id = max(self.track_new_id, track.id) + 1

        except KeyboardInterrupt:
            raise KeyboardInterrupt
        except:
            pass

    def save_crawled_entries(self):
        elems = []
        for track in self.tracks:
            elems.append(track.__dict__)

        with open(song_path, "w", encoding="utf-8") as f:
            json.dump(elems, f, indent=2, ensure_ascii=False)

    def show_artists(self):
        for artist in self.artists:
            print(artist, end=", ")

    def filter_tracks(self):
        print("Excluding pre-filtered artists, and songs with forbidden characters..")
        with open(exclude_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)

            forbidden_artists = json_data["exclude_artist"]
            forbidden_uri = json_data["exclude_uri"]

            new_tracks = []

            for track in self.tracks:
                if track.artist in forbidden_artists:
                    print(f"Filter: Track {track.title} is by forbidden artist {track.artist}")
                    continue

                if track.yt_uri in forbidden_uri:
                    print(f"Filter: Track {track.title} has forbidden URI")
                    continue

                if bool(forbidden_regex.search(track.title.split("(")[0])):
                    print(f"Track {track.title} - {track.artist} has forbidden character")
                    continue

                if track.title.lower().find("remix") >= 0:
                    print(f"Track {track.title} is remix")
                    continue

                new_tracks.append(track)

            self.tracks = new_tracks

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

            dist_str = SongManager.dist_str(title, artist)
            
            if dist_str not in self.track_dist_set:
                new_id = self.track_new_id
                self.track_new_id += 1
                self.track_dist_set.add(dist_str)
                self.tracks.append(Track(new_id, title, artist))
                self.artists.add(artist)

    def query_melon_on_top100(self):
        query_url_string = "https://www.melon.com/chart/index.htm"

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

            dist_str = SongManager.dist_str(title, artist)
            
            if dist_str not in self.track_dist_set:
                new_id = self.track_new_id
                self.track_new_id += 1
                self.track_dist_set.add(dist_str)
                self.tracks.append(Track(new_id, title, artist))
                self.artists.add(artist)

    def query_melon(self):
        for year in range(2010, 2025):
            self.query_melon_by_year(year)
        
        self.query_melon_on_top100()

    def query_youtube_link(self, track: Track):
        search_keyword = f"{track.title} {track.artist} 가사"
        search_keyword = search_keyword.replace(" ", "+")
        search_keyword = search_keyword.replace("#", "%23")
        query_url = f"https://www.youtube.com/results?search_query={search_keyword}"

        self.driver.get(query_url)
        time.sleep(3)
        res = self.driver.page_source
        soup = BeautifulSoup(res, "html.parser")

        list_container = soup.find("ytd-two-column-search-results-renderer", class_="ytd-search")
        vid_blocks = list_container.find_all("ytd-video-renderer", class_="ytd-item-section-renderer")

        # Use the first video.. but skip if the video is too long.
        for vid_block in vid_blocks:
            vid_dismissible = vid_block.find("div", id="dismissible", recursive=False)
            vid_thumbnail = vid_dismissible.find("ytd-thumbnail")
            vid_metadata = vid_dismissible.find("div", class_="text-wrapper")

            vid_len_elem = vid_thumbnail.find("div", class_="yt-badge-shape__text").text
            len_list = list(map(int, vid_len_elem.split(":")))

            vid_uri_a = vid_block.find("a", class_="yt-simple-endpoint")
            vid_href = vid_uri_a.attrs["href"]
            vid_uri = vid_href.split("&")[0].split("=")[-1]

            vid_title_a = vid_metadata.find("a", id="video-title")
            vid_title = vid_title_a.attrs["title"]

            vid_length = 0
            weight = 1
            for i in range(len(len_list)):
                index = -1 - i
                vid_length += len_list[index] * weight
                weight *= 60

            if vid_length <= 600:
                # Under 10 minutes: It should be correct video.

                track.yt_vid_length = vid_length
                track.yt_vid_title = vid_title
                track.yt_uri = vid_uri

                return


    def fetch_youtube_links(self):
        batch = 0

        for track in self.tracks:
            if track.yt_uri is None:
                self.query_youtube_link(track)
                batch += 1

                if batch % 10 == 0:
                    print(f"Collected {batch}.. save.")
                    self.save_crawled_entries()

        self.save_crawled_entries()

    def download_youtube_video_by_one(self, track: Track):
        file_path = base_dir.parent / f"songs/{track.yt_uri}.opus"

        if os.path.exists(file_path):
            # If there is already a file, skip.
            return

        # Otherwise, let's make a file and send it to remote server, if doesn't existed!
        print(f"Downloading {track.title} {track.artist}..")

        yt_url = f"https://www.youtube.com/watch?v={track.yt_uri}"
        try:
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                ydl.download([yt_url])

        except KeyboardInterrupt:
            raise KeyboardInterrupt
        except:
            print(f"Download failed on track {track.title}\n\t{yt_url}")


    def download_youtube_audios(self):
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self.download_youtube_video_by_one, track): track for track in self.tracks}
            success = 0

            for _ in as_completed(futures):
                success += 1

if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-m', "--melon", action="store_true", help="query melon chart to collect basic database of songs.")
    arg_parser.add_argument('-y', "--youtube", action="store_true", help="find YT links for queried tracks.")
    arg_parser.add_argument('-d', "--download", action="store_true", help="download audio files with given YT links.")
    arg_parser.add_argument('-f', "--filter", action="store_true", help="filter artists with exclusion list 'forbidden_artists.json'")
    arg_parser.add_argument('-e', "--explore", action="store_true", help="explore data, implement your custom action for traveling song data.")
    args = arg_parser.parse_args()

    manager = SongManager()
    
    if args.melon:
        manager.run_webdriver()
        manager.load_crawled_entries()
        manager.query_melon()
        manager.save_crawled_entries()

    elif args.filter:
        manager.load_crawled_entries()
        manager.filter_tracks()
        manager.save_crawled_entries()

    elif args.youtube:
        manager.run_webdriver()
        manager.load_crawled_entries()
        manager.fetch_youtube_links()

    elif args.download:
        manager.load_crawled_entries()
        manager.download_youtube_audios()

    elif args.explore:
        manager.load_crawled_entries()

        s = {}

        for track in manager.tracks:
            if track.yt_uri in s:
                print(f"Duplicate: {track.id} and {s[track.yt_uri].id}")

            s[track.yt_uri] = track

        print(len(manager.tracks))
        print(len(s))

    else:
        print("Usage: data.py [OPTIONS]")