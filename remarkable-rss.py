from urllib.request import Request, urlopen
import shutil
import json
import os
import feedparser
from datetime import datetime
import textwrap
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fpdf import FPDF
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload
from goose3 import Goose
import subprocess

# Edit the following according to your preferences.
MAX_RETRIES = 10  # Amount of Network-Error based request retries
WD = os.path.dirname(os.path.realpath(__file__))  # Current working Directory
HTML_DIR = "HTML_Out"  # Storage location for the extracted HTML source
TEMP_FILE = 'temp.txt'  # A temporary storage file for downloaded text

FEED_URLS = []
EBOOK_NAMES = []

f = open("feeds.txt", "r")
d = json.loads(f.read())
for i in d:
    FEED_URLS.append(d[i])
    EBOOK_NAMES.append(i)

# Generate the file path for saving the RSS data
date_str = datetime.now().strftime('%Y-%m-%d')
file_path = f"RSS-Feed_{date_str}"
EBOOK_NAME = f"{file_path}.pdf"

def rss_to_ebook(my_url,my_name):
    # Create HTML storage dir
    if os.path.exists(HTML_DIR):
        shutil.rmtree(HTML_DIR, ignore_errors=True)
    os.mkdir(HTML_DIR)
    d = feedparser.parse(my_url)

    # Enumerate through our feed, store the 'clean' article text in our temporary file, before exporting it to HTML
    for c, e in enumerate(d.entries):
        url = e.link
        print('Processing - {}'.format(url))
        g = Goose()
        retries = MAX_RETRIES
        while retries > 0:
            try:
                req = Request(url)
                req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:106.0) Gecko/20100101 Firefox/106.0')
                req.add_header('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8')
                req.add_header('Accept-Language', 'en-US,en;q=0.5')
                webpage = urlopen(req).read()
                g = Goose()
                article = g.extract(raw_html=webpage)
                g.close
                break
            except Exception as e:
                print('Error establishing connection. Retrying...')
                retries -= 1
        if retries <= 0:
            print('Failed to retreive article ({}). Moving on to next feed item.'.format(url))
            retries = MAX_RETRIES
        with open('temp.txt', 'w') as file:
            file.write(article.cleaned_text)
        of = HTML_DIR + '/s{}-{}.html'.format('{0:05d}'.format(c+1), url.split("/")[-1].split(".")[0])
        subprocess.Popen('pandoc -i temp.txt -t html5 -o {}'.format(of), cwd=WD, shell=True).wait()
        with open(of, 'r+') as f:
            content = f.read()
            f.seek(0, 0)
            f.write('<h1>{}</h1>'.format(article.title).rstrip('\r\n') + '\n' + content)
        # Feed title and Link are required as per the RSS2 spec ... we don't check if there's actually a value
        with open(HTML_DIR + '/s00000.html', 'w') as file:
            file.write('<!DOCTYPE html><html><head><meta name="author" content="{}" />'
                       '<title>{}</title></head></html>'.format(d.feed.link, d.feed.title))
    # Convert the directory of (Ordered HTML file's into a single EPub)
    subprocess.Popen('pandoc --variable "geometry=margin=1.2in" --variable mainfont="Palatino" --variable sansfont="Helvetica" --variable monofont="Menlo" --variable fontsize=12pt -s -i {}/*.html -t pdf -o {} --toc'.format(HTML_DIR, my_name),  cwd=WD, shell=True).wait()

    # Cleanup
    os.remove('temp.txt')

# Load environment variables
load_dotenv()

# Retrieve folder ID and service.json file
SERVICE_ACCOUNT_FILE = os.getenv('SERVICE_ACCOUNT_FILE')
FOLDER_ID = os.getenv('FOLDER_ID')

# Validate the presence of required environment variables
if not SERVICE_ACCOUNT_FILE or not FOLDER_ID:
    raise ValueError("Both SERVICE_ACCOUNT_FILE and FOLDER_ID environment variables must be set.")

# Define the scopes for Google Drive access
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def upload_to_google_drive(file_path, folder_id=None):
    """Upload a file to Google Drive."""
    credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('drive', 'v3', credentials=credentials)

    file_metadata = {
        'name': os.path.basename(file_path),
        'mimeType': 'application/pdf',  # Assuming you are uploading a PDF file
    }
    if folder_id:  # Include folder_id if provided
        file_metadata['parents'] = [folder_id]

    media = MediaFileUpload(file_path, mimetype='application/pdf')
    try:
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print(f"Uploaded to Google Drive with file ID: {file.get('id')}")
    except Exception as e:
        print(f"Upload to Google Drive failed: {e}")

if __name__ == "__main__":
    for i, u in enumerate(FEED_URLS):
        rss_to_ebook(u,EBOOK_NAMES[i])
        # Upload the PDF to Google Drive
        upload_to_google_drive(EBOOK_NAMES[i], FOLDER_ID)
