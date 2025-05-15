import platform
import subprocess
import sys
import os
import shutil
import logging as log

MTP_NAMESPACE_ID = 17

class MTPManager:
    def __init__(self):
        self.platform = platform.system()
        self.mtp_namespace = None
        self.shell = None
        self.ensure_pywin32()

    def ensure_pywin32(self):
        if platform.system() == "Windows":
            try:
                import win32com.client
            except ImportError:
                print("pywin32 is not installed. Installing...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", "pywin32"])
                subprocess.check_call([sys.executable, "-m", "pywin32_postinstall"])
                print("pywin32 installed successfully.")
            finally :
                self.init_windows_mtp()

    def init_windows_mtp(self):
        try:
            import win32com.client
            self.shell = win32com.client.Dispatch("Shell.Application")
            self.mtp_namespace = self.shell.NameSpace(MTP_NAMESPACE_ID)  # MTP Namespace ID
            if self.mtp_namespace is None:
                log.error("MTP namespace could not be initialized.")
        except ImportError as e:
            log.error(f"Windows MTP initialization failed: {e}")

    def is_MTP_available(self):
        if self.platform == "Windows":
            return self.mtp_namespace is not None

        elif self.platform in ["Linux", "Darwin"]:
            try:
                subprocess.run(["mtp-detect"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return True
            except FileNotFoundError:
                log.error("MTP not available (libmtp not installed).")
                return False

        log.warning("Unsupported platform for MTP.")
        return False

    def list_mtp_devices(self):
        if not self.is_MTP_available():
            log.warning("MTP is not available on this system.")
            return []

        if self.platform == "Windows":
            devices = []

            for device in self.mtp_namespace.Items():
                if device.Name.startswith("DWARF"):
                    devices.append((device.Name, device.Path))
            return devices

        elif self.platform in ["Linux", "Darwin"]:
            result = subprocess.run(["mtp-detect"], capture_output=True, text=True)
            return result.stdout.splitlines()

        return []

    # Full Path Mtp Directory for MTP Device
    def getFullPathOfMtpDir(self, mtpDir):

        if not self.is_MTP_available():
            log.warning("MTP is not available on this system.")
            return ""

        if platform.system() == "Windows":

            fullDirPath = ""
            lastDirPath = ""
            directory = mtpDir.GetFolder
            while directory:
            
                print(f"ParentFolder: {directory.ParentFolder}")
                if directory.ParentFolder:
                    lastDirPath = fullDirPath
                    fullDirPath =  os.path.join(directory.Title, fullDirPath)
                directory = directory.ParentFolder;
            
            print(f"fullDirPath: {fullDirPath}")
            print(f"lastDirPath: {lastDirPath}")
            return lastDirPath

        elif platform.system() in ["Linux", "Darwin"]:
            return ""

    # get Files from MTP Device
    async def get_files_from_mtp(self, device_id, subdir_name, progress_label):
        if not self.is_MTP_available():
            log.warning("MTP is not available on this system.")
            return []

        if platform.system() == "Windows":

            for device in self.mtp_namespace.Items():
                if device.Path == device_id:
                    astronomy_folder = device.GetFolder.ParseName("MTP\\sdcard\\DWARF_II\\Astronomy")
                    if astronomy_folder:
                        subfolder = astronomy_folder.GetFolder.ParseName(subdir_name)
                        if subfolder:
                            print(f"subfolder: {subfolder}")
                            items = list(subfolder.GetFolder.Items())
                            return items
                        else:
                            progress_label.set_text("Selected subdirectory not found.")
                            return []
                    else:
                        progress_label.set_text("Astronomy folder not found.")
                        return []

        elif platform.system() in ["Linux", "Darwin"]:
            return ""

    async def get_folder_from_mtp(self, destination):
        if not self.is_MTP_available():
            log.warning("MTP is not available on this system.")
            return ""

        if platform.system() == "Windows":

            # Define the destination path
            full_path = os.path.abspath(destination)
            os.makedirs(full_path, exist_ok=True)
            dest_folder = self.shell.NameSpace(full_path)

            return dest_folder

        elif platform.system() in ["Linux", "Darwin"]:
            return ""

    async def copy_file_from_mtp(self, file, mtp_folder):
        if not self.is_MTP_available():
            log.warning("MTP is not available on this system.")
            return False

        if platform.system() == "Windows":
            import win32com.client
            if mtp_folder:
                mtp_folder.CopyHere(file)
                return True
            else:
                return False

        elif platform.system() in ["Linux", "Darwin"]:
            return False

    # Copy Files from MTP Device
    async def copy_files_from_mtp(self, device_id, subdir_name, destination, progress_bar, progress_label):
        if not self.is_MTP_available():
            progress_label.set_text("MTP not available on this system.")
            log.warning("MTP is not available on this system.")
            return

        if platform.system() == "Windows":

            # Define the destination path
            full_path = os.path.abspath(destination)
            dest_folder = self.shell.NameSpace(full_path)
            os.makedirs(destination, exist_ok=True)
            print(f"full_path: {full_path}")

            for device in self.mtp_namespace.Items():
                if device.Path == device_id:
                    astronomy_folder = device.GetFolder.ParseName("MTP\\sdcard\\DWARF_II\\Astronomy")
                    if astronomy_folder:
                        subfolder = astronomy_folder.GetFolder.ParseName(subdir_name)
                        if subfolder:
                            print(f"subfolder: {subfolder}")
                            items = list(subfolder.GetFolder.Items())
                            total_files = len(items)

                            if total_files == 0:
                                progress_label.set_text("No files to copy.")
                                return

                            # Find the specific file 
                            await run.io_bound(copy_files_with_progress, items, dest_folder, total_files, progress_bar, progress_label)
                            return
                        else:
                            progress_label.set_text("Selected subdirectory not found.")
                    else:
                        progress_label.set_text("Astronomy folder not found.")

        elif platform.system() in ["Linux", "Darwin"]:
            return

    # Function to copy files with progress tracking
    def copy_files_with_progress(self, items, dest_folder, total_files, progress_bar, progress_label):
        if not self.is_MTP_available():
            progress_label.set_text("MTP not available on this system.")
            log.warning("MTP is not available on this system.")
            return

        if platform.system() == "Windows":

            for i, item in enumerate(items):
                print(f"Copying: {item.Name}")
                dest_folder.CopyHere(item)
                progress = (i + 1) / total_files
                update_progress(progress_bar, progress_label, progress, i + 1, total_files)

        elif platform.system() in ["Linux", "Darwin"]:
            return

    # List Subdirectories in Astronomy Folder
    def list_subdirectories(self, device_id):
        if not self.is_MTP_available():
            log.warning("MTP is not available on this system.")
            return []

        if platform.system() == "Windows":

            for device in self.mtp_namespace.Items():
                if device.Path == device_id:
                    astronomy_folder = device.GetFolder.ParseName("MTP\\sdcard\\DWARF_II\\Astronomy")
                    if not astronomy_folder:
                        return []
                    return [item.Name for item in astronomy_folder.GetFolder.Items() if item.IsFolder]

        elif platform.system() in ["Linux", "Darwin"]:
            return []

    def copy_folder_contents(self, folder, destination):
        if not self.is_MTP_available():
            log.warning("MTP is not available on this system.")
            return False

        if platform.system() == "Windows":
            os.makedirs(destination, exist_ok=True)
            for item in folder.GetFolder.Items():
                if item.IsFolder:
                    copy_folder_contents(item, os.path.join(destination, item.Name))
                else:
                    print(f"Copying: {item.Name}")
                    temp_folder = os.path.join(os.getenv("TEMP"), item.Name)
                    item.InvokeVerb("copy")
                    shutil.copy(temp_folder, os.path.join(destination, item.Name))
            return True

        elif platform.system() in ["Linux", "Darwin"]:
            return False

    # Debug: List Files in Selected Subdirectory
    def list_files_in_subdirectory(self, device_id, subdir_name, notification_label):
        if not self.is_MTP_available():
            notification_label.set_text("MTP not available on this system.")
            log.warning("MTP is not available on this system.")
            return

        if platform.system() == "Windows":

            for device in self.mtp_namespace.Items():
                if device.Path == device_id:
                    astronomy_folder = device.GetFolder.ParseName("MTP\\sdcard\\DWARF_II\\Astronomy")
                    if astronomy_folder:
                        subfolder = astronomy_folder.GetFolder.ParseName(subdir_name)
                        if subfolder is not None:
                            file_list = []
                            for item in subfolder.GetFolder.Items():  # Ensure we are accessing GetFolder
                                file_list.append(item.Name)
                            if file_list:
                                notification_label.set_text(f"Files in {subdir_name}: {', '.join(file_list)}")
                            else:
                                notification_label.set_text(f"No files found in {subdir_name}.")
                        else:
                            notification_label.set_text("Subdirectory not found.")
                    else:
                        notification_label.set_text("Astronomy folder not found.")

        elif platform.system() in ["Linux", "Darwin"]:
            return False
