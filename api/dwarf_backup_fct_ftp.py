import os
import ftplib
from ftplib import FTP

from contextlib import contextmanager

from api.dwarf_backup_fct import print_log

DWARF2_FTP_PATH = "/DWARF_II/Astronomy"
DWARF3_FTP_PATH = "/Astronomy"

@contextmanager
def ftp_conn(ip_address):
    ftp = ftplib.FTP()
    try:
        ftp.connect(ip_address)
        ftp.login()  # Anonymous login
        yield ftp
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()

def get_ftp_astroDir(ip_address):
    if not ip_address:
        return None

    try:
        with ftp_conn(ip_address) as ftp:
            dwarf2_path = DWARF2_FTP_PATH
            dwarf3_path = DWARF3_FTP_PATH

            if dwarf2_path in ftp.nlst("/DWARF_II"):
                return dwarf2_path
            elif dwarf3_path in ftp.nlst("/"):
                return dwarf3_path
    except ftplib.all_errors:
        pass

    return None

def list_ftp_subdirectories(ip_address):
    if not ip_address:
        return None

    try:
        with ftp_conn(ip_address) as ftp:
            if DWARF2_FTP_PATH in ftp.nlst("/DWARF_II"):
                return ftp.nlst(DWARF2_FTP_PATH)
            elif DWARF3_FTP_PATH in ftp.nlst("/"):
                return ftp.nlst(DWARF3_FTP_PATH)
    except ftplib.all_errors:
        pass

    return []

def ftp_path_exists(ip_address, path):
    try:
        with ftp_conn(ip_address) as ftp:
            ftp.cwd(path)
            return True
    except:
        return False

def check_ftp_connection(ip_address):
    if not ip_address:
        return "❌ Please enter an IP address."

    try:
        with ftp_conn(ip_address) as ftp:
            if DWARF2_FTP_PATH in ftp.nlst("/DWARF_II"):
                return "✅ Connected to Dwarf2 FTP"
            elif DWARF3_FTP_PATH in ftp.nlst("/"):
                return "✅ Connected to Dwarf3 FTP"
            else:
                return "❌ Connected to FTP (not Dwarf)."
    except ftplib.all_errors:
        return "❌ FTP Error: not connected"

def download_ftp_tree(ip_address, ftp_root_path, local_dest_root):
    all_files = []
    try:
        with ftp_conn(ip_address) as ftp:
            _recursive_ftp_walk(ftp, ftp_root_path, local_dest_root, all_files)
    except ftplib.all_errors as e:
        print(f"FTP error: {e}")
    return all_files

def _recursive_ftp_walk(ftp, ftp_path, local_dest_root, all_files):
    try:
        entries = ftp.nlst(ftp_path)
        for entry in entries:
            try:
                ftp.cwd(entry)  # It's a directory
                _recursive_ftp_walk(
                    ftp, entry,
                    os.path.join(local_dest_root, os.path.relpath(entry, ftp_path)),
                    all_files
                )
            except ftplib.error_perm:
                # It's a file
                rel_path = os.path.relpath(entry, ftp_path)
                local_path = os.path.join(local_dest_root, rel_path)
                all_files.append((entry, local_path))
    except ftplib.all_errors as e:
        print(f"FTP error listing {ftp_path}: {e}")

def ftp_walk(ftp, path):
    """
    Generator that mimics os.walk for an FTP path.
    Yields (current_path, directories, files)
    """
    dirs, nondirs = [], []

    try:
        entries = ftp.nlst(path)
        for entry in entries:
            # Skip . and ..
            name = entry.rsplit('/', 1)[-1]
            if name in ('.', '..'):
                continue

            try:
                ftp.cwd(entry)  # Try to change into the entry
                dirs.append(entry)
            except ftplib.error_perm:
                nondirs.append(entry)

        yield path, dirs, nondirs

        for subdir in dirs:
            yield from ftp_walk(ftp, subdir)

    except ftplib.error_perm:
        pass  # Path doesn't exist or no permission

# Function to connect to Dwarf via FTP
def connect_to_dwarf(ip_address, status_label):
    status_message = check_ftp_connection(ip_address)
    if status_label:
        status_label.text = status_message

# --- Download file from FTP to local ---
def ftp_download_file(ftp, remote_path, local_path):
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, 'wb') as f:
        ftp.retrbinary(f"RETR {remote_path}", f.write)

# --- Upload file from local to FTP ---
# not working as READ ONLY need sftp on DWARF 2 only
def ftp_upload_file(ftp, local_path, remote_path):
    with open(local_path, 'rb') as f:
        ftp.storbinary(f"STOR {remote_path}", f)

def files_are_different(dst, size):
    if not os.path.exists(dst):
        return True
    if os.path.getsize(dst) != size:
        return True
    return False

def safe_path(path):
    abspath = os.path.abspath(path)
    if os.name == 'nt':
        return f"\\\\?\\{abspath}"
    return abspath

def ftp_sync_dwarf_sessions(ftp, dwarf_id, source_root="/DWARF/Sessions", local_root="./Dwarf_Local", log=None):
    dwarf_dir = os.path.join(local_root, f"DWARF_{dwarf_id}")
    archive_dir = os.path.join(dwarf_dir, "Archive")
    os.makedirs(archive_dir, exist_ok=True)

    ftp.cwd(source_root)
    sessions = ftp.nlst()

    local_sessions = [
        d for d in os.listdir(dwarf_dir)
        if os.path.isdir(os.path.join(dwarf_dir, d)) and d != "Archive"
    ]

    print_log(f"🔄 Syncing {len(sessions)} sessions from FTP...", log)

    for session in sessions:
        remote_session_path = f"{source_root}/{session}"
        dst_session = os.path.join(dwarf_dir, session)
        os.makedirs(dst_session, exist_ok=True)

        ftp.cwd(remote_session_path)
        files = ftp.nlst()
        for file_name in files:
            if file_name.startswith("stacked") or file_name == "shotsInfo.json":
                local_file_path = safe_path(os.path.join(dst_session, file_name))

                # Get size from FTP (needed to compare)
                size = ftp.size(file_name)

                if files_are_different(local_file_path, size):
                    print_log(f"📥 Downloading {file_name} from {session}...", log)
                    with open(local_file_path, 'wb') as f:
                        ftp.retrbinary(f"RETR {file_name}", f.write)
                else:
                    print_log(f"✅ Skipping {file_name} (unchanged)", log)

    # Archive removed sessions
    removed_sessions = set(local_sessions) - set(sessions)
    for session in removed_sessions:
        src_path = os.path.join(dwarf_dir, session)
        dst_path = os.path.join(archive_dir, session)
        print_log(f"📦 Archiving removed session: {session}", log)
        shutil.move(src_path, dst_path)

    print_log("✅ FTP sync complete.", log)













# --- Ensure remote FTP path exists (optional) ---
def ftp_ensure_dirs(ftp, remote_path, created_dirs_cache):
    """
    Ensure directories exist for a given remote_path.
    Uses a set cache to avoid re-checking/making same folders.
    """
    dirs = remote_path.strip("/").split("/")[:-1]
    current_path = ""
    for d in dirs:
        current_path += f"/{d}"
        if current_path in created_dirs_cache:
            continue
        try:
            ftp.mkd(current_path)
        except ftplib.error_perm as e:
            if not str(e).startswith("550"):
                raise  # Re-raise unexpected errors
        created_dirs_cache.add(current_path)

def parse_shots_info(json_path, ftp=None):
    try:
        if json_path.startswith("ftp://"):
            # Handle FTP case
            if not ftp:
                print(f"❌ FTP connection is required for {json_path}.")
                return {}

            # Extracting the path on FTP server
            ftp_path = json_path.replace("ftp://", "")
            with open("temp_shotsInfo.json", "wb") as temp_file:
                ftp.retrbinary(f"RETR {ftp_path}", temp_file.write)

            with open("temp_shotsInfo.json", 'r', encoding='utf-8') as f:
                raw = json.load(f)

        else:
            # Local file handling
            with open(json_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)

        return {
            "dec": str(raw.get("DEC")),
            "ra": str(raw.get("RA")),
            "target": raw.get("target"),
            "binning": raw.get("binning"),
            "format": raw.get("format"),
            "exp_time": str(raw.get("exp")) if raw.get('exp') is not None else None,
            "gain": raw.get("gain"),
            "shotsToTake": raw.get("shotsToTake"),
            "shotsTaken": raw.get("shotsTaken"),
            "shotsStacked": raw.get("shotsStacked"),
            "ircut": raw.get("ir"),
            "maxTemp": raw.get("maxTemp"),
            "minTemp": raw.get("minTemp"),
        }

    except Exception as e:
        print(f"Error reading {json_path}: {e}")
        return {}

def compute_md5(filepath):
    hash_md5 = hashlib.md5()
    filepath_str = str(filepath)
    if filepath_str.startswith("ftp://"):
        # For FTP, read the file in chunks
        url_parts = filepath[6:].split('/', 1)
        ftp_host = url_parts[0]
        ftp_path = url_parts[1]
        with ftplib.FTP(ftp_host) as ftp:
            ftp.login()  # Anonymous by default
            with ftp.transfercmd(f'RETR {ftp_path}') as conn:
                while chunk := conn.recv(4096):
                    hash_md5.update(chunk)
    else:
        long_path = f"\\\\?\\{os.path.abspath(filepath)}"
        with open(long_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)

    return hash_md5.hexdigest()

# Function to parse shotsInfo.json
def extract_target_json_ftp(ip_address, astro_path):
    json_path = f"{astro_path}/shotsInfo.json"
    meta = {}

    try:
        with ftp_conn(ip_address) as ftp:
            buffer = io.BytesIO()
            ftp.retrbinary(f"RETR {json_path}", buffer.write)
            buffer.seek(0)
            meta = json.load(buffer)
    except Exception as e:
        # Optional: print(f"❌ Could not load {json_path} from FTP: {e}")
        meta = {}

    return meta.get("target") if meta else None


## TO DO ##
def scan_backup_folder_ftp(db_name, backup_root, astronomy_dir, dwarf_id, backup_drive_id = None, session_dir_path = None, log=None):
    if not db_name:
        print_log(f"❌ database name can not be empty!",log)
        return 0,0
    conn = connect_db(db_name)
    if not conn:
        print_log(f"❌ {db_name} database couldn't be opened!",log)
        return 0,0

    if astronomy_dir:
        data_root = os.path.join(backup_root, astronomy_dir)
    else:
        data_root = backup_root
    if not os.path.exists(data_root):
        print_log(f"❌ {astronomy_dir} folder not found in {backup_root}",log)
        return 0,0

    # Scan only one session dir
    session_dir_main_dir = None
    session_dir = None
    is_session_dir = None

    if session_dir_path:
        session_dir_main_dir, is_session_dir = determine_session_dir(data_root, session_dir_path)

    if session_dir_main_dir:
        session_dir = os.path.basename(session_dir_path)

    valid_ids = set()
    total_added = 0
    deleted = 0

    for astro_dir in os.listdir(data_root):
        astro_path = os.path.join(data_root, astro_dir)
        if not os.path.isdir(astro_path):
            continue

        if session_dir_main_dir and not (session_dir_main_dir == astro_dir):
            continue

        if session_dir_main_dir:
            if is_session_dir:
                print_log(f"🔍 Processing Session Dir: {session_dir}",log)
                print(f"🔍 Processing Session Dir: {session_dir}",log)

        else:
            print_log(f"🔍 Processing Dir:",log)
            print_log(f"🔍 {astro_dir}",log)
            print(f"astro_path Dir: {astro_path}")
            print(f"Processing Dir: {astro_dir}")
    
        found_data = False
        total_previous = total_added
    
        astro_name = extract_astro_name_from_folder(astro_dir)
        print(f"Processing extract_astro_name_from_folder: {astro_name}")
        if not astro_name:
            check_target_file = astro_path
            print(f"check_target_file Dir: {astro_path}")
            astro_name = extract_target_json(astro_path)
            print(f"Processing extract_target_json: {astro_name}")
        if astro_name:
            found_data = True
            astro_object_id, new = insert_astro_object(conn, astro_name)
            if not astro_object_id:
                break
            if new:
                print_log(f"add astro object : {astro_name}",log)
            else:
                print_log(f"use astro object : {astro_name}",log)
            print_log(f"📂 Processing direct Dwarf data:\n {astro_dir}",log)
            new_added, data_ids = process_dwarf_folder(
                conn, backup_root, astro_path,
                astro_object_id, dwarf_id, backup_drive_id
            )
            total_added += new_added
            if data_ids:
                if isinstance(data_ids, (list, tuple, set)):
                    valid_ids.update(data_ids)
                else:
                    valid_ids.add(data_ids)
            if total_added - total_previous == 1:
                print_log(f"📂 Found 1 new Session in {astro_dir}",log)
            elif total_added != total_previous:
                print_log(f"📂 Found {total_added - total_previous} new Sessions in {astro_dir}",log)

        else:
            astro_name = astro_dir
            # Traverse all folders below astro_path
            for root, dirs, files in os.walk(astro_path):
                if check_dir_session (root, dirs, files, session_dir_main_dir, session_dir):
                    current_dir = os.path.basename(os.path.normpath(root))
                    print(f"current_dir Dir: {current_dir}")
                    if current_dir == 'Thumbnail':
                        last_dir = os.path.basename(os.path.dirname(root))  # Use parent dir
                        last_dir = os.path.basename(os.path.dirname(root))  # name
                        last_dir_path = os.path.dirname(root)               # full path
                    else:
                        last_dir = current_dir
                        last_dir_path = root
                    print(f"check_target_file Dir: {last_dir}")
                    check_target = extract_astro_name_from_folder(last_dir)
                    if not check_target:
                        print(f"check_target_file Dir: {last_dir_path}")
                        check_target = extract_target_json(last_dir_path)

                    print(f"check_target: {check_target}")
                    if check_target:
                        if not found_data:
                            print(f"not found_data")
                            if astro_name == "RESTACKED":
                                astro_object_id, new = insert_astro_object(conn, check_target)
                                if not astro_object_id:
                                    break
                                if new:
                                    print_log(f"add astro object : {check_target}",log)
                                else:
                                    print_log(f"use astro object : {check_target}",log)
                                found_data = True
                            else: # use Main AstroDir Name
                                print(f"astro_object_id {astro_name}")
                                astro_object_id, new = insert_astro_object(conn, astro_name)
                                if not astro_object_id:
                                    print(f"not astro_object_id")
                                    break
                                if new:
                                    print_log(f"add astro object : {astro_name}",log)
                                else:
                                    print_log(f"use astro object : {astro_name}",log)
                                found_data = True
                        print_log(f"📂 Processing session folder (deep):\n {os.path.dirname(last_dir_path)}",log)
                        print_log(f"📂 Session: {os.path.basename(last_dir_path)}",log)
                        print(f"Processing session folder (deep): {last_dir_path}")
                        new_added, data_ids = process_dwarf_folder(
                            conn, backup_root, last_dir_path,
                            astro_object_id, dwarf_id, backup_drive_id
                        )
                        total_added += new_added
                        print(f"Added : {new_added}")
                        if data_ids:
                            if isinstance(data_ids, (list, tuple, set)):
                                valid_ids.update(data_ids)
                            else:
                                valid_ids.add(data_ids)

            if total_added - total_previous == 1:
                print_log(f"📂 Found 1 new Session in {astro_dir}",log)
            elif total_added != total_previous:
                print_log(f"📂 Found {total_added - total_previous} new Sessions in {astro_dir}",log)
            else:
                print_log(f"📂 No new Session found in {astro_dir}",log)

        if not found_data:
            print_log(f"⚠️ Ignored unrecognized folder: {astro_dir}",log)

    if session_dir_main_dir :
        # update scan date if modifications presents
        if deleted or total_added:
            set_dwarf_scan_date(conn, dwarf_id)

    else:
        # delete data that are not more present
        if not backup_drive_id:
            deleted = delete_notpresent_dwarf_entries_and_dwarf_data(conn, dwarf_id, valid_ids)
            if deleted == 1:
                print_log(f"📂 Deleted 1 entry in DB not more present",log)
            elif deleted and deleted > 1:
                print_log(f"📂 deleted {deleted} entries in DB not more present",log)
            # update scan date if modifications presents
            if deleted or total_added:
                set_dwarf_scan_date(conn, dwarf_id)
        else:
            deleted = delete_notpresent_backup_entries_and_dwarf_data(conn, backup_drive_id, valid_ids)
            if deleted == 1:
                print_log(f"📂 Deleted 1 entry in DB not more present",log)
            elif deleted and deleted > 1:
                print_log(f"📂 deleted {deleted} entries in DB not more present",log)
            # update scan date if modifications presents
            if deleted or total_added:
                set_backup_scan_date(conn, backup_drive_id)

    commit_db(conn)
    close_db(conn)
    return total_added, deleted

