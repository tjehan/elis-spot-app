#! /usr/bin/env python
# -*- coding: utf-8 -*-

from flask import Flask, request, render_template, redirect, url_for
from keys import SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET
from threading import Thread
from queue import Queue
import spotipy
import spotipy.oauth2 as oauth2
import random
import time


def list_argsort(seq):
    return sorted(range(len(seq)), key=seq.__getitem__, reverse=True)


def one_track_per_artist_and_album(items):
    artist_ids = []
    album_ids = []
    new_items = []
    random.shuffle(items)
    for item in items:
        artist_id = item['artists'][0]['id']
        album_id = item['album']['id']
        if artist_id in set(artist_ids) or album_id in set(album_ids):
            continue
        artist_ids.append(artist_id)
        album_ids.append(album_id)
        new_items.append(item)
    return new_items


def filter_by_duration(items, minsec=120, maxsec=600):
    new_items = []
    for item in items:
        if item['duration_ms'] < minsec * 1000 or item['duration_ms'] > maxsec * 1000:
            continue
        new_items.append(item)
    return new_items


def filter_tracks(items, minsec=120, maxsec=600):
    with open('christmas_title_blacklist.txt') as f:
        blacklist = [line.rstrip() for line in f]
    new_items = []
    for item in items:
        if item['duration_ms'] < minsec * 1000 or item['duration_ms'] > maxsec * 1000:
            continue
        if item['name'] in blacklist:
            continue
        new_items.append(item)
    return new_items


class Spot(object):
    """
        A class that handles basic Spotify music personalization.
        It interfaces with the Spotify Web API and can create 3 playlists:
            - Top personalization: some of the user's favorite tracks
            - Safe personalization: top songs from the user's favorite artists
            - Adventurous personalization: recommended songs based on the user's taste
        Each of these playlists are sorted from energetic to mellow
    """

    def __init__(
            self,
            _sp=None
    ):

        self.sp = _sp
        self.username = _sp.current_user()['id']

    def get_top_tracks(self, limit=20):
        items = []
        results = self.sp.current_user_saved_tracks(limit=30)
        items.extend([item['track'] for item in results['items']])
        results = self.sp.current_user_top_tracks(time_range='long_term', limit=40)
        items.extend(results['items'])
        results = self.sp.current_user_top_tracks(time_range='medium_term', limit=20)
        items.extend(results['items'])
        results = self.sp.current_user_top_tracks(time_range='short_term', limit=10)
        items.extend(results['items'])
        items = one_track_per_artist_and_album(items)
        items = filter_tracks(items)
        if items:
            items = random.sample(items, k=min(limit, len(items)))
        return items

    def get_random_top_tracks_for_artists(self, artists):
        items = []
        for artist in artists['items']:
            res = self.sp.artist_top_tracks(artist['id'])
            try:
                items.append(random.choice(res['tracks']))
            except:
                print("Exception in get_random_top_tracks_for_artists:", artist['id'], artist['name'])
        return items

    def get_safe_tracks(self, limit=20):
        items = []
        results = self.sp.current_user_top_artists(time_range='long_term', limit=55)
        items.extend(self.get_random_top_tracks_for_artists(results))
        results = self.sp.current_user_top_artists(time_range='medium_term', limit=30)
        items.extend(self.get_random_top_tracks_for_artists(results))
        results = self.sp.current_user_top_artists(time_range='short_term', limit=15)
        items.extend(self.get_random_top_tracks_for_artists(results))
        items = one_track_per_artist_and_album(items)
        items = filter_tracks(items)
        if items:
            items = random.sample(items, k=min(limit, len(items)))
        return items

    def get_discover_weekly_tracks(self, limit=30):
        offset = 0
        results = self.sp.user_playlists(user=self.username, limit=50, offset=offset)
        while results['items']:
            for playlist in results['items']:
                if playlist['name'] == 'Discover Weekly':
                    break
            if playlist['name'] == 'Discover Weekly':
                break
            offset += 50
            results = self.sp.user_playlists(user=self.username, limit=50, offset=offset)
        if playlist['name'] == 'Discover Weekly':
            results = self.sp.playlist_tracks(playlist_id=playlist['id'])
            items = [item['track'] for item in results['items']]
            if items:
                items = random.sample(items, k=min(limit, len(items)))
            return items

    def get_recommendations_for_artists(self, artist_ids, limit=20):
        results = self.sp.recommendations(seed_artists=artist_ids, limit=limit)
        return results['tracks']

    def get_recommendations_for_tracks(self, track_ids, limit=20):
        results = self.sp.recommendations(seed_tracks=track_ids, limit=limit)
        return results['tracks']

    def get_recommendations_from_top_artist(self, limit=50):
        items = []
        num_seeds = 5
        results = self.sp.current_user_top_artists(time_range='long_term', limit=int(round(limit / 5)))
        artist_ids = [artist['id'] for artist in results['items']]
        for i in range((len(artist_ids) + num_seeds - 1) // num_seeds):
            sub_artist_ids = artist_ids[i * num_seeds:(i + 1) * num_seeds]
            items.extend(self.get_recommendations_for_artists(sub_artist_ids, limit=25))
        if items:
            items = random.sample(items, k=min(limit, len(items)))
        return items

    def get_recommendations_from_top_tracks(self, limit=100):
        items = []
        num_seeds = 5
        results = self.sp.current_user_top_tracks(time_range='long_term', limit=int(round(limit / 5)))
        track_ids = [track['id'] for track in results['items']]
        for i in range((len(track_ids) + num_seeds - 1) // num_seeds):
            sub_track_ids = track_ids[i * num_seeds:(i + 1) * num_seeds]
            items.extend(self.get_recommendations_for_tracks(sub_track_ids, limit=25))
        if items:
            items = random.sample(items, k=min(limit, len(items)))
        return items

    def get_adventurous_tracks(self, limit=20):
        items = []
        items.extend(self.get_discover_weekly_tracks(limit=30))
        items.extend(self.get_recommendations_from_top_artist(limit=50))
        items.extend(self.get_recommendations_from_top_tracks(limit=50))
        items = one_track_per_artist_and_album(items)
        items = filter_tracks(items)
        if items:
            items = random.sample(items, k=min(limit, len(items)))
        return items

    def get_tracks(self, level='top', limit=20):
        if level == 'top':
            tracks = self.get_top_tracks(limit)
        elif level == 'safe':
            tracks = self.get_safe_tracks(limit)
        elif level == 'adventurous':
            tracks = self.get_adventurous_tracks(limit)
        else:
            return []
        if tracks:
            tids = [track['uri'] for track in tracks]
            features = [feature['energy'] for feature in self.sp.audio_features(tids)]
            args = list_argsort(features)
            return [tracks[i] for i in args]
        else:
            return []

    def create_playlist(self, tracks=None, name=None, description=None):
        found = False
        results = self.sp.user_playlists(user=self.username, limit=50, offset=0)
        for playlist in results['items']:
            if playlist['name'] == name:
                found = True
                break
        if found is False:
            playlist = self.sp.user_playlist_create(user=self.username, name=name, public=False,
                                                    description=description)
        track_ids = [track['id'] for track in tracks]
        self.sp.user_playlist_replace_tracks(user=self.username, playlist_id=playlist['id'], tracks=track_ids)


# create the flask application
app = Flask(__name__)

# SPOTIPY_REDIRECT_URI = 'https://elisspot-dot-elisspot.appspot.com'
SPOTIPY_REDIRECT_URI = 'http://127.0.0.1:8080'
CACHE = '.spotipyoauthcache'  # not used online
SCOPE = 'user-library-read user-follow-read user-top-read user-read-currently-playing ' \
        'playlist-read-private playlist-modify-private'

sp_oauth = oauth2.SpotifyOAuth(SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI, scope=SCOPE,
                               cache_path=CACHE, show_dialog=True)

spot = None
thread = None
queue = Queue()


@app.route('/', methods=["POST", "GET"])
def index():
    global spot

    access_token = ""
    token_info = sp_oauth.get_cached_token()
    token_info = []  # hack for now

    if token_info:
        print("Found cached token!")
        access_token = token_info['access_token']
    else:
        url = request.url
        code = sp_oauth.parse_response_code(url)
        if code:
            print("Found Spotify auth code in Request URL! Trying to get valid access token...")
            token = sp_oauth.get_access_token(code)
            access_token = token if type(token) == 'str' else token['access_token']
    if access_token:
        print("Access token available! Creating spotify object.")
        spot = Spot(spotipy.Spotify(auth=access_token))
        return redirect(url_for("run"))
    else:
        auth_url = sp_oauth.get_authorize_url()
        return render_template("index.html", auth_url=auth_url)


@app.route("/run", methods=['POST', 'GET'])
def run():
    global thread, queue

    if thread is not None:
        if thread.is_alive():
            progress = queue.get()
            return render_template("running.html", progress=progress)
        else:
            thread.join()
            thread = None
            queue.queue.clear()
            return redirect(url_for("success"))
    else:
        thread = Thread(target=createPlaylists, args=[queue])
        thread.start()
        return render_template("running.html", progress=1)


@app.route("/success")
def success():
    auth_url = sp_oauth.get_authorize_url()
    return render_template("success.html", auth_url=auth_url)


def createPlaylists(queue):
    global spot

    queue.put(10)
    tracks = spot.get_tracks(level='adventurous', limit=30)
    name = "Elis Adventurous"
    description = "Adventurous personalization for Elis"
    queue.put(25)
    spot.create_playlist(tracks=tracks, name=name, description=description)
    queue.put(40)
    tracks = spot.get_tracks(level='safe', limit=30)
    name = "Elis Safe"
    description = "Safe personalization for Elis"
    queue.put(60)
    spot.create_playlist(tracks=tracks, name=name, description=description)
    queue.put(80)
    tracks = spot.get_tracks(level='top', limit=30)
    name = "Elis Top"
    description = "Top personalization for Elis"
    spot.create_playlist(tracks=tracks, name=name, description=description)
    queue.put(100)
    time.sleep(1)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
