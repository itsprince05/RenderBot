import os
from dotenv import load_dotenv

load_dotenv()

# Get these from https://my.telegram.org
API_ID = os.getenv("API_ID", "38659771")
API_HASH = os.getenv("API_HASH", "6178147a40a23ade99f8b3a45f00e436")
BOT_TOKEN = os.getenv("BOT_TOKEN", "7872058354:AAF5u6AYO3yovIPMa8rs-VSXvFmhK9x46e8")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6701020399"))
Admins_Group_ID = -1003609401157
Normal_Media_Group_ID = -1003674205198
Self_Distruct_Media_Group_ID = -1003592103153
Details_Group_ID = -1003407091550
Backup_Group_ID = -1003701083974
Logs_Group_ID = -1003837883832
import json

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DIR = os.path.join(BASE_DIR, "users")
FILTER_FILE = os.path.join(BASE_DIR, "filter_user.json")

def load_filters():
    if os.path.exists(FILTER_FILE):
        try:
            with open(FILTER_FILE, "r") as f:
                data = json.load(f)
                return data.get("IGNORED_USERS", []), data.get("DOWNLOAD_FILTER_ADMINS", [])
        except Exception:
            pass
    # Default initialize
    default_data = {
        "IGNORED_USERS": [],
        "DOWNLOAD_FILTER_ADMINS": [632695771, 7260591725, 8218943149, 6701020399]
    }
    with open(FILTER_FILE, "w") as f:
        json.dump(default_data, f, indent=4)
    return default_data["IGNORED_USERS"], default_data["DOWNLOAD_FILTER_ADMINS"]

auth_filters = load_filters()
IGNORED_USERS = auth_filters[0]
DOWNLOAD_FILTER_ADMINS = auth_filters[1]

def save_filters():
    with open(FILTER_FILE, "w") as f:
        json.dump({
            "IGNORED_USERS": IGNORED_USERS, 
            "DOWNLOAD_FILTER_ADMINS": DOWNLOAD_FILTER_ADMINS
        }, f, indent=4)
