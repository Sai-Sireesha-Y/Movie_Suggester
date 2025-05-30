import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import ast
import os
import requests
import time
import threading

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
CSV_FILE = os.path.join(DATA_DIR, "movies.csv")

# Ensure the data directory exists
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# --- TMDb API Configuration ---

TMDB_API_KEY = "335e7eb8eecc8a794ac44112a31349d5"
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# --- Helper Functions for API Calls ---

def get_genres_from_api():
    """Fetches movie genres from TMDb API."""
    url = f"{TMDB_BASE_URL}/genre/movie/list?api_key={TMDB_API_KEY}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return {genre['id']: genre['name'] for genre in data['genres']}
    except requests.exceptions.RequestException as e:
        print(f"Error fetching genres from API: {e}")
        return {}

def get_all_languages_from_api():
    """Fetches all official language list from TMDb API."""
    url = f"{TMDB_BASE_URL}/configuration/languages?api_key={TMDB_API_KEY}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return {lang['iso_639_1']: lang['english_name'] for lang in data if lang['iso_639_1']}
    except requests.exceptions.RequestException as e:
        print(f"Error fetching languages from API: {e}")
        return {}

# --- Data Collection Function (runs in a separate thread) ---
def collect_and_save_movie_data_threaded(app_instance, num_pages_per_language=10):
    """
    Collects movie data from TMDb API and saves it to a CSV file.
    This function is designed to be run in a separate thread.
    It updates the GUI via app_instance.
    """
    app_instance.update_status("Starting data collection...")

    genres_map = get_genres_from_api()
    if not genres_map:
        app_instance.update_status("Error: Could not retrieve genres. Data collection failed.")
        return

    all_tmdb_languages = get_all_languages_from_api()
    if not all_tmdb_languages:
        app_instance.update_status("Error: Could not retrieve languages. Data collection failed.")
        return

    languages_to_collect_subset = {
        "en": "English", "hi": "Hindi", "es": "Spanish", "fr": "French", "de": "German",
        "ja": "Japanese", "ko": "Korean", "it": "Italian", "bn": "Bengali", "gu": "Gujarati",
        "kn": "Kannada", "ml": "Malayalam", "pa": "Punjabi", "ta": "Tamil", "te": "Telugu",
        "zh": "Chinese", "ru": "Russian", "ar": "Arabic", "pt": "Portuguese", "tr": "Turkish",
        "sv": "Swedish", "da": "Danish", "no": "Norwegian", "fi": "Finnish", "pl": "Polish",
        "nl": "Dutch", "th": "Thai", "id": "Indonesian", "vi": "Vietnamese", "el": "Greek",
        "cs": "Czech", "hu": "Hungarian", "ro": "Romanian", "fa": "Persian", "he": "Hebrew",
        "ur": "Urdu"
    }

    active_languages_for_collection = {
        code: name for code, name in languages_to_collect_subset.items() if code in all_tmdb_languages
    }

    all_movies_data = []
    processed_movie_ids = set()

    total_languages = len(active_languages_for_collection)
    app_instance.update_status(f"Collecting data across {total_languages} languages and {num_pages_per_language} pages per language...")

    for i, (lang_code, lang_name) in enumerate(active_languages_for_collection.items()):
        app_instance.update_status(f"Collecting for {lang_name} ({i+1}/{total_languages})...")
        for page in range(1, num_pages_per_language + 1):
            url = f"{TMDB_BASE_URL}/discover/movie?api_key={TMDB_API_KEY}&sort_by=popularity.desc&language={lang_code}&page={page}"
            try:
                response = requests.get(url)
                response.raise_for_status()
                data = response.json()

                if not data['results']:
                    app_instance.update_status(f"  No more results for {lang_name} on page {page}.")
                    break

                for movie in data['results']:
                    if movie['id'] in processed_movie_ids:
                        continue

                    genre_names = [genres_map.get(gid, "Unknown") for gid in movie.get('genre_ids', [])]
                    all_movies_data.append({
                        'id': movie['id'],
                        'title': movie['title'],
                        'original_language': movie['original_language'],
                        'fetched_language_code': lang_code,
                        'fetched_language_name': lang_name,
                        'genre_ids': str(movie.get('genre_ids', [])),
                        'genres_list': str(genre_names),
                        'popularity': movie.get('popularity', 0),
                        'vote_average': movie.get('vote_average', 0),
                        'release_date': movie.get('release_date', ''),
                        'overview': movie.get('overview', '')
                    })
                    processed_movie_ids.add(movie['id'])

                app_instance.update_status(f"  Fetched page {page} for {lang_name}. Total unique movies: {len(all_movies_data)}")
                time.sleep(0.2) # Be polite to the API

            except requests.exceptions.RequestException as e:
                app_instance.update_status(f"  Error fetching page {page} for {lang_name}: {e}")
                if hasattr(response, "status_code") and response.status_code == 429:
                    app_instance.update_status("  Rate limit hit. Waiting for 60 seconds...")
                    time.sleep(60)
                continue
            except Exception as e:
                app_instance.update_status(f"  An unexpected error occurred for page {page} and {lang_name}: {e}")
                continue

    if all_movies_data:
        df = pd.DataFrame(all_movies_data)
        os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)
        df.to_csv(CSV_FILE, index=False)
        app_instance.update_status(f"Successfully collected {len(df)} unique movies and saved to {CSV_FILE}")
    else:
        app_instance.update_status("No movie data collected.")

    # Reload data and update dropdowns after collection
    app_instance.master.after(100, app_instance.load_data)
    app_instance.master.after(200, app_instance.populate_dropdowns)
    app_instance.master.after(300, lambda: app_instance.update_status("Data collection complete. App ready."))

# --- Main GUI Application Class ---
class MovieApp:
    def __init__(self, master):
        self.master = master
        master.title("Movie Suggester")
        master.geometry("400x450")

        # Frame for controls
        self.control_frame = ttk.Frame(master, padding="10")
        self.control_frame.pack(fill=tk.X, pady=10)

        # Status Label
        self.status_label = tk.Label(master, text="Status: Initializing...", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        # Collect Data Button
        self.collect_button = tk.Button(self.control_frame, text="Collect/Update Movie Data", command=self.start_data_collection)
        self.collect_button.grid(row=0, column=0, columnspan=2, pady=10)

        # Genre Selection
        self.genre_label = tk.Label(self.control_frame, text="Select Genre:")
        self.genre_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.genre_combobox = ttk.Combobox(self.control_frame, state="readonly")
        self.genre_combobox.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # Language Selection
        self.language_label = tk.Label(self.control_frame, text="Select Language:")
        self.language_label.grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.language_combobox = ttk.Combobox(self.control_frame, state="readonly")
        self.language_combobox.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        # Configure column weights for resizing
        self.control_frame.grid_columnconfigure(1, weight=1)

        # Get Movies Button
        self.get_movies_button = tk.Button(master, text="Get Top 20 Movies", command=self.display_movies)
        self.get_movies_button.pack(pady=10)

        # Movie List Display
        self.movie_list_label = tk.Label(master, text="Top 20 Movies:")
        self.movie_list_label.pack(pady=5)
        
        self.movie_list_text = tk.Text(master, height=15, width=60, wrap=tk.WORD, font=("Arial", 10))
        self.movie_list_text.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        self.movie_list_text.config(state=tk.DISABLED)

        # Now it's safe to load data (widgets exist)
        self.df = None
        self.load_data()

        # Populate dropdowns initially (even if CSV is empty, it will use API for lists)
        self.populate_dropdowns()

        # Check if CSV exists on startup and prompt for collection if not
        if self.df is None or self.df.empty:
            messagebox.showinfo("Initial Setup", "No movie data found. Please click 'Collect/Update Movie Data' to download some.")
            self.update_status("No data loaded. Click 'Collect/Update Movie Data'.")
            self.get_movies_button.config(state=tk.DISABLED) # Disable until data is present
        else:
            self.update_status(f"Loaded {len(self.df)} movies from CSV.")
            self.get_movies_button.config(state=tk.NORMAL) # Ensure enabled if data is present
    
    def load_data(self):
        """Loads movie data from the CSV file."""
        if not os.path.exists(CSV_FILE):
            self.df = None
            return

        try:
            self.df = pd.read_csv(CSV_FILE)
            for col in ['genre_ids', 'genres_list']:
                if col in self.df.columns:
                    self.df[col] = self.df[col].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
            self.update_status(f"Successfully loaded {len(self.df)} movies from {CSV_FILE}")
            self.get_movies_button.config(state=tk.NORMAL)
        except Exception as e:
            messagebox.showerror("CSV Load Error", f"Error loading CSV file: {e}\n"
                                                  "Please ensure the CSV is not corrupt and its path is correct.")
            self.df = None
            self.get_movies_button.config(state=tk.DISABLED)
            
    def update_status(self, message):
        self.status_label.config(text=f"Status: {message}")
        self.master.update_idletasks()
        
    
            
    def populate_dropdowns(self):
        all_genres_from_data = set()
        if self.df is not None and 'genres_list' in self.df.columns and not self.df['genres_list'].empty:
            for genres_str_or_list in self.df['genres_list'].dropna():
                try:
                    genres_list = ast.literal_eval(genres_str_or_list) if isinstance(genres_str_or_list, str) else genres_str_or_list
                    if isinstance(genres_list, list):
                        for genre_name in genres_list:
                            if isinstance(genre_name, str):
                                all_genres_from_data.add(genre_name)
                except (ValueError, SyntaxError):
                    continue

        if not all_genres_from_data:
            self.update_status("Warning: Could not extract genres from CSV. Fetching from TMDb API.")
            tmdb_genre_map = get_genres_from_api()
            if tmdb_genre_map:
                all_genres_from_data = set(tmdb_genre_map.values())
            else:
                self.update_status("Error: Could not retrieve genres from CSV or TMDb API. Genre dropdown will be empty.")

        self.genre_names = sorted(list(all_genres_from_data))
        self.genre_combobox['values'] = self.genre_names
        if self.genre_names:
            self.genre_combobox.set(self.genre_names[0])

        self.all_tmdb_languages_map = get_all_languages_from_api()
        if not self.all_tmdb_languages_map:
            self.update_status("Error: Could not retrieve languages from TMDb API. Language dropdown will be empty.")
            self.display_language_names = []
            self.language_name_to_code = {}
        else:
            self.display_language_names = sorted(list(self.all_tmdb_languages_map.values()))
            self.language_name_to_code = {v: k for k, v in self.all_tmdb_languages_map.items()}

        self.language_combobox['values'] = self.display_language_names
        if "English" in self.display_language_names:
            self.language_combobox.set("English")
        elif self.display_language_names:
            self.language_combobox.set(self.display_language_names[0])

    def start_data_collection(self):
        if messagebox.askyesno("Confirm Data Collection", 
                               "This will download movie data from TMDb and save it to a CSV file.\n"
                               "This might take some time and requires an internet connection.\n"
                               "Do you want to proceed?"):
            self.collect_button.config(state=tk.DISABLED)
            self.get_movies_button.config(state=tk.DISABLED)
            self.update_status("Data collection initiated. Please wait...")

            collection_thread = threading.Thread(target=collect_and_save_movie_data_threaded, args=(self, 10))
            collection_thread.daemon = True
            collection_thread.start()
        else:
            self.update_status("Data collection cancelled.")

    def display_movies(self):
        if self.df is None or self.df.empty:
            messagebox.showerror("Error", "No movie data loaded. Please collect data first.")
            return

        selected_genre_name = self.genre_combobox.get()
        selected_display_language_name = self.language_combobox.get()

        if not selected_genre_name or not selected_display_language_name:
            messagebox.showwarning("Input Error", "Please select both a genre and a language.")
            return

        selected_language_code = self.language_name_to_code.get(selected_display_language_name)

        if selected_language_code is None:
            messagebox.showerror("Error", "Selected language not found in TMDb language list. This should not happen.")
            return

        self.movie_list_text.config(state=tk.NORMAL)
        self.movie_list_text.delete(1.0, tk.END)

        filtered_by_language = self.df[self.df['fetched_language_code'] == selected_language_code]

        filtered_movies = filtered_by_language[
            filtered_by_language['genres_list'].apply(lambda x: selected_genre_name in x if isinstance(x, list) else False)
        ]

        if not filtered_movies.empty:
            top_movies = filtered_movies.sort_values(by='popularity', ascending=False).head(20)
            for i, row in enumerate(top_movies.itertuples()):
                self.movie_list_text.insert(tk.END, f"{i+1}. {row.title}\n")
        else:
            self.movie_list_text.insert(
                tk.END,
                "No titles found for the selected language and genre combination in the collected data.\n"
                "Try collecting more data using 'Collect/Update Movie Data' or choose different criteria."
            )

        self.movie_list_text.config(state=tk.DISABLED)

def main():
    root = tk.Tk()
    app = MovieApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()