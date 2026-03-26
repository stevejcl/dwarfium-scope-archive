import posixpath
import socket
import logging
import stat
from contextlib import asynccontextmanager
import asyncssh
# Encoding changed to UTF-8
log = logging.getLogger(__name__)

@asynccontextmanager
async def asyncssh_sftp_session(ip_address, username="root", password="rockchip"):
    ssh = None
    sftp = None
    try:
        ssh = await asyncssh.connect(ip_address, username=username, password=password, known_hosts=None)
        sftp = await ssh.start_sftp_client()
        yield sftp
    except (socket.timeout, EOFError, OSError) as e:
        log.error(f"SFTP session failed due to timeout or connection issue: {e}")
        raise
    except Exception as e:
        log.error(f"SSH/SFTP session failed: {e}")
        raise
    finally:
        if sftp:
            sftp.exit()
        if ssh:
            ssh.close()
            await ssh.wait_closed()

async def ensure_remote_dir(sftp, local_file_path):
    dir_path = posixpath.dirname(local_file_path)
    parts = dir_path.strip("/").split("/")
    current = ""
    for part in parts:
        current = f"{current}/{part}"
        try:
            await sftp.stat(current)
        except Exception as e:
            try:
                print(f"SFTP Creating remote dir: {current}")
                await sftp.mkdir(current)
            except Exception as e:
                print(f"[FAIL] Failed to create {current}: {e}")
                raise

async def async_sftp_upload(ip_address, remote_file_path, local_file_path, created_dirs_cache):
    async with asyncssh_sftp_session(ip_address) as sftp:
            print(f"Uploading {remote_file_path} → {local_file_path}")
            dir_path = posixpath.dirname(local_file_path)
            if dir_path not in created_dirs_cache:
                print(f"Checking\n  {dir_path}")
                await ensure_remote_dir(sftp, local_file_path)
                created_dirs_cache.add(dir_path)

            try: 
                await sftp.put(remote_file_path, local_file_path)
                print(f"Uploaded Succes")
            except (socket.timeout, EOFError, OSError) as e:
                log.error(f"SFTP async_sftp_upload failed due to timeout or connection issue: {e}")
                raise
            except Exception as e:
                log.error(f"SSH/SFTP async_sftp_upload failed: {e}")
                raise

async def sftp_clean_subdir_files(ip_address: str, remote_dest_dir: str) -> None:
    """For Repair mode (Dwarf 2 SFTP): delete all files inside subdirectories
    of remote_dest_dir. Subdirectory structure is preserved, root-level files
    are untouched.
    """
    async with asyncssh_sftp_session(ip_address) as sftp:
        try:
            entries = await sftp.readdir(remote_dest_dir)
        except Exception as e:
            log.warning(f"SFTP clean: cannot list {remote_dest_dir}: {e}")
            return

        for entry in entries:
            if entry.filename in (".", ".."):
                continue
            remote_path = posixpath.join(remote_dest_dir, entry.filename)
            # Only descend into subdirectories
            if not stat.S_ISDIR(entry.attrs.permissions):
                continue
            try:
                files = await sftp.readdir(remote_path)
            except Exception as e:
                log.warning(f"SFTP clean: cannot list {remote_path}: {e}")
                continue
            for f in files:
                if f.filename in (".", ".."):
                    continue
                if stat.S_ISREG(f.attrs.permissions):
                    remote_file = posixpath.join(remote_path, f.filename)
                    try:
                        await sftp.remove(remote_file)
                        log.info(f"SFTP clean: removed {remote_file}")
                    except Exception as e:
                        log.warning(f"SFTP clean: failed to remove {remote_file}: {e}")