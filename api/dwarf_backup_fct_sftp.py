import posixpath
import socket
import logging
from contextlib import asynccontextmanager
import asyncssh

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
                print(f"❌ Failed to create {current}: {e}")
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
