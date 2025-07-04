import platform
import subprocess
import sys
import os
import shutil
import logging as log

# Encoding changed to UTF-8
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
                self.init_windows_mtp()
            except ImportError:
                log.error("pywin32 is not correcly installed.")
                log.error("use: python -m pip install -r requirements-windows.txt")

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
                            if progress_label:
                                progress_label.set_text("Selected subdirectory not found.")
                            else:
                                log.warning("Selected subdirectory not found.")

                            return []
                    else:
                        if progress_label:
                            progress_label.set_text("Astronomy folder not found.")
                        else:
                            log.error("Selected subdirectory not found.")
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

    def copy_folder_contents(self, folder, destination):
        if not self.is_MTP_available():
            log.warning("MTP is not available on this system.")
            return False

        if platform.system() == "Windows":
            os.makedirs(destination, exist_ok=True)
            mtp_destination = self.get_folder_from_mtp(destination)
            for item in folder.GetFolder.Items():
                if item.IsFolder:
                    copy_folder_contents(item, os.path.join(destination, item.Name))
                else:
                    print(f"Copying: {item.Name}")
                    self.copy_file_from_mtp(item.Name, mtp_destination)
            return True

        elif platform.system() in ["Linux", "Darwin"]:
            return False

    # Debug: List Files in Selected Subdirectory
    def list_files_in_subdirectory(self, device_id, subdir_name, notification_label):
        if not self.is_MTP_available():
            if notification_label:
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
                                if notification_label:
                                    notification_label.set_text(f"Files in {subdir_name}: {', '.join(file_list)}")
                                else:
                                    log.info(f"Files in {subdir_name}: {', '.join(file_list)}")
                            else:
                                if notification_label:
                                    notification_label.set_text(f"No files found in {subdir_name}.")
                                else:
                                    log.warning(f"No files found in {subdir_name}.")
                        else:
                            if notification_label:
                                notification_label.set_text("Subdirectory not found.")
                            else:
                                log.warning("Subdirectory not found.")
                    else:
                        if notification_label:
                            notification_label.set_text("Astronomy folder not found.")
                        else:
                            log.error("Astronomy folder not found.")

        elif platform.system() in ["Linux", "Darwin"]:
            return False

