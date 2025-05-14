import os
import sqlite3
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, messagebox

from api.dwarf_backup_fct import scan_backup_folder, open_folder, insert_or_get_backup_drive 

from api.dwarf_backup_db import connect_db, close_db, commit_db

from api.dwarf_backup_db_api import get_dwarf_Names, get_dwarf_detail, set_dwarf_detail, add_dwarf_detail
from api.dwarf_backup_db_api import get_backupDrive_detail, set_backupDrive_detail, get_backupDrive_list, get_backupDrive_id_from_location, add_backupDrive_detail, del_backupDrive
from api.dwarf_backup_db_api import get_session_present_in_Dwarf, get_session_present_in_backupDrive
from api.dwarf_backup_db_api import has_related_backup_entries, delete_backup_entries_and_dwarf_data, delete_dwarf_entries_and_dwarf_data

from cli.dwarf_backup_explore import ExploreApp

class ConfigApp:
    def __init__(self, master, database):
        self.master = master
        self.database = database
        self.conn = connect_db(self.database)
        self.master.title("Dwarf Config Tool")
        self.dwarfs = []
        self.dwarf_id = None
        self.backupDrives = []
        self.backupDrive_id = None

        self.dwarf_type_map = {
            1: "Dwarf2",
            2: "Dwarf3"
        }
        self.dwarf_type_name_to_id = {v: k for k, v in self.dwarf_type_map.items()}

        tk.Button(master, text="Show All Current Backup Data", command=self.show_data).grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="w")
        tk.Button(master, text="Show All Current Dwarf Data", command=self.show_dwarf_data).grid(row=0, column=2, columnspan=2, padx=10, pady=10, sticky="w")
        ttk.Separator(master, orient="horizontal").grid(row=1, column=0, columnspan=3, sticky="ew", pady=15)

        # --- Dwarf Selection ---
        tk.Label(master, text="Select Existing Dwarf").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.dwarf_var = tk.StringVar()
        self.dwarf_combobox = ttk.Combobox(master, textvariable=self.dwarf_var, state="readonly")
        self.dwarf_combobox.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        # Bind selection to automatic loading
        self.dwarf_combobox.bind("<<ComboboxSelected>>", lambda e: self.load_selected_dwarf())

        # --- "Add New Dwarf" Button ---
        tk.Button(master, text="➕ Add New Dwarf", command=self.set_new_dwarf).grid(row=2, column=2, padx=5, pady=5)

        # --- Dwarf Fields ---
        tk.Label(master, text="Dwarf Name").grid(row=3, column=0, sticky="e", padx=15)
        self.dwarf_name = tk.Entry(master)
        self.dwarf_name.grid(row=3, column=1, sticky="w", padx=5)

        tk.Label(master, text="Description").grid(row=4, column=0, sticky="e", padx=15)
        self.dwarf_desc = tk.Entry(master)
        self.dwarf_desc.grid(row=4, column=1, sticky="w", padx=5)

        tk.Label(master, text="Astronomy Directory").grid(row=5, column=0, sticky="e", padx=15)
        self.dwarf_astroDir = tk.Entry(master, width=40)
        self.dwarf_astroDir.grid(row=5, column=1, sticky="w", padx=5)

        tk.Button(master, text="Select USB Folder", command=lambda: self.select_dwarf_folder()).grid(row=5, column=2)

        tk.Label(master, text="Type").grid(row=6, column=0, sticky="e", padx=15)

        self.dwarf_type_var = tk.StringVar()
        self.dwarf_type_combobox = ttk.Combobox(master, textvariable=self.dwarf_type_var, state="readonly")
        self.dwarf_type_combobox["values"] = list(self.dwarf_type_map.values())
        self.dwarf_type_combobox.current(1)  # Default to Dwarf3
        self.dwarf_type_combobox.grid(row=6, column=1, sticky="w", padx=5, pady=5)

        tk.Button(master, text="Analyze USB Drive", command=self.analyze_usb_drive).grid(row=7, column=0, sticky="ew", padx=5, pady=(15,30))
        tk.Button(master, text="Save / Update Dwarf", command=self.save_or_update_dwarf).grid(row=7, column=1, sticky="w", padx=5, pady=(15,30))
        tk.Button(master, text="🗑️ Delete Dwarf Entries", command=self.confirm_and_delete_dwarf_entries, fg="red").grid(row=7, column=2, padx=5, pady=(15,30))

        # --- BackupDrive section ---
        tk.Label(master, text="Select Existing BackupDrive").grid(row=8, column=0, padx=5, pady=5, sticky="e")
        self.backupDrive_var = tk.StringVar()
        self.backupDrive_combobox = ttk.Combobox(master, textvariable=self.backupDrive_var, state="readonly")
        self.backupDrive_combobox.grid(row=8, column=1, padx=5, pady=5, sticky="w")

        # Bind selection to automatic loading
        self.backupDrive_combobox.bind("<<ComboboxSelected>>", lambda e: self.load_selected_backupDrive())

        # --- "Add New BackupDrive" Button ---
        tk.Button(master, text="➕ Add New BackupDrive", command=self.set_new_BackupDrive).grid(row=8, column=2, padx=5, pady=5)

        tk.Label(master, text="Backup Drive Name").grid(row=9, column=0, sticky="e", padx=15)
        self.backupDrive_name = tk.Entry(master)
        self.backupDrive_name.grid(row=9, column=1, sticky="w", padx=5)
        tk.Button(master, text="🗑️ Delete Backup Drive", command=self.confirm_and_delete_BackupDrive, fg="red").grid(row=9, column=2, padx=5, pady=15)

        tk.Label(master, text="Drive Description").grid(row=10, column=0, sticky="e", padx=15)
        self.backupDrive_desc = tk.Entry(master, width=40)
        self.backupDrive_desc.grid(row=10, column=1, sticky="w", padx=5)

        tk.Label(master, text="Location").grid(row=11, column=0, sticky="e", padx=15)
        self.backupDrive_location = tk.Entry(master, width=40)
        self.backupDrive_location.grid(row=11, column=1, sticky="w", padx=5)

        tk.Button(master, text="Select Folder", command=self.select_folder).grid(row=11, column=2)

        tk.Label(master, text="Astronomy Directory").grid(row=12, column=0, sticky="e", padx=15)
        self.backupDrive_astroDir = tk.Entry(master, width=40)
        self.backupDrive_astroDir.grid(row=12, column=1, sticky="w", padx=5)

        tk.Button(master, text="Select Sub Folder", command=lambda: self.select_subfolder(self.backupDrive_location)).grid(row=12, column=2)

        tk.Label(master, text="Dwarf").grid(row=13, column=0, sticky="e", padx=15)
        self.backupDrive_dwarf_var = tk.StringVar()
        self.backupDrive_dwarf_combobox = ttk.Combobox(master, textvariable=self.backupDrive_dwarf_var, state="readonly")
        self.backupDrive_dwarf_combobox.grid(row=13, column=1, padx=5, pady=5, sticky="w")

        tk.Button(master, text="Save / Update Backup Drive", command=self.save_or_update_backup_drive).grid(row=14, column=1, sticky="w", padx=5, pady=15)
        tk.Button(master, text="Analyze Current Drive", command=self.analyze_drive).grid(row=14, column=0, sticky="ew", padx=5, pady=15)
        tk.Button(master, text="🗑️ Delete Backup Entries", command=self.confirm_and_delete_entries, fg="red").grid(row=14, column=2, padx=5, pady=15)

        self.refresh_dwarf_list()
        self.refresh_backupDrive_list()

    def refresh_dwarf_list(self):
        self.dwarfs = get_dwarf_Names(self.conn)

        display_names = [f"{id} - {name}" for id, name in self.dwarfs]
        self.dwarf_combobox["values"] = display_names

        self.dwarf_name_to_id = {name: id_ for id_, name in self.dwarfs}
        self.dwarf_id_to_name = {id_: name for id_, name in self.dwarfs}
        self.backupDrive_dwarf_combobox["values"] = list(self.dwarf_name_to_id.keys())

        self.dwarf_var.set("")

        # Optionally set default
        if self.dwarfs:
           self.backupDrive_dwarf_var.set(self.dwarfs[0][1])

    def load_selected_dwarf(self):
        value = self.dwarf_var.get()
        if not value:
            return
        try:
            self.dwarf_id = int(value.split(" - ")[0])  # Extracts "1" from "1 - Dwarf3"
        except (IndexError, ValueError):
            print("Invalid dwarf selection.")
            return

        row = get_dwarf_detail(self.conn, self.dwarf_id)
        if row:
            self.dwarf_name.delete(0, tk.END)
            self.dwarf_name.insert(0, row[0])
            self.dwarf_desc.delete(0, tk.END)
            self.dwarf_desc.insert(0, row[1] or "")
            self.dwarf_astroDir.delete(0, tk.END)
            self.dwarf_astroDir.insert(0, row[2] or "")
            self.dwarf_type_combobox.set(self.dwarf_type_map[int(row[3])])

    def set_new_dwarf(self):
        self.dwarf_id = None
        self.dwarf_name.delete(0, tk.END)
        self.dwarf_desc.delete(0, tk.END)
        self.dwarf_astroDir.delete(0, tk.END)
        self.dwarf_type_combobox.set(self.dwarf_type_map[2])

    def select_dwarf_folder(self):
        dwarf_location = self.dwarf_astroDir.get().strip()
        if dwarf_location:
            folder = filedialog.askdirectory(initialdir=dwarf_location)
        else:
            folder = filedialog.askdirectory()
        if folder:
            folder = os.path.normpath(folder)
            self.dwarf_astroDir.delete(0, tk.END)
            self.dwarf_astroDir.insert(0, folder)

    def save_or_update_dwarf(self):
        name = self.dwarf_name.get()
        desc = self.dwarf_desc.get()
        usb_astronomy_dir = self.dwarf_astroDir.get()

        selected_type = self.dwarf_type_var.get()
        dtype = self.dwarf_type_name_to_id.get(selected_type, 1) 

        if not name:
            messagebox.showerror("Error", "Name is required")
            return

        if self.dwarf_id:  # Update
            set_dwarf_detail(self.conn, name, desc, usb_astronomy_dir, dtype, self.dwarf_id)
            messagebox.showinfo("Updated", f"Dwarf '{name}' updated.")
        else:  # Insert
            self.dwarf_id = add_dwarf_detail(self.conn, name, desc, usb_astronomy_dir, dtype)
            messagebox.showinfo("Saved", f"Dwarf '{name}' created with ID {self.dwarf_id}")

        self.refresh_dwarf_list()

    def refresh_backupDrive_list(self):
        self.backupDrives = get_backupDrive_list(self.conn)

        display_names = [f"{id} - {name}" for id, name, description, location, astrodir, dwarf_id, scan_date in self.backupDrives]
        self.backupDrive_combobox["values"] = display_names

        self.backupDrive_var.set("")

    def load_selected_backupDrive(self):
        value = self.backupDrive_var.get()
        if not value:
            return
        try:
            self.backupDrive_id = int(value.split(" - ")[0])  # Extracts "1" from "1 - Name"
        except (IndexError, ValueError):
            print("Invalid dwarf selection.")
            return

        row = get_backupDrive_detail(self.conn, self.backupDrive_id)

        if row:
            self.backupDrive_name.delete(0, tk.END)
            self.backupDrive_name.insert(0, row[0])
            self.backupDrive_desc.delete(0, tk.END)
            self.backupDrive_desc.insert(0, row[1] or "")
            self.backupDrive_location.delete(0, tk.END)
            self.backupDrive_location.insert(0, row[2] or "")
            self.backupDrive_astroDir.delete(0, tk.END)
            self.backupDrive_astroDir.insert(0, row[3] or "")
            self.backupDrive_dwarf_var.set(row[4] or "")

    def set_new_BackupDrive(self):
        self.backupDrive_id = None
        self.backupDrive_name.delete(0, tk.END)
        self.backupDrive_desc.delete(0, tk.END)
        self.backupDrive_location.delete(0, tk.END)
        self.backupDrive_astroDir.delete(0, tk.END)
        if self.dwarfs:
            self.backupDrive_dwarf_var.set(self.dwarfs[0][1])

    def select_folder(self):
        location = self.backupDrive_location.get().strip()
        if location:
            folder = filedialog.askdirectory(initialdir=location)
        else:
            folder = filedialog.askdirectory()
        if folder:
            folder = os.path.normpath(folder)
            self.backupDrive_location.delete(0, tk.END)
            self.backupDrive_location.insert(0, folder)

    def select_subfolder(self, location_entry):
        location = location_entry.get().strip()
        if not location:
            messagebox.showerror("Error", "Fill Location first.")
            return

        base_path = os.path.normpath(location)
        subfolder = filedialog.askdirectory(initialdir=base_path, title="Select Subfolder")

        if subfolder:
            subfolder = os.path.normpath(subfolder)

            if subfolder and subfolder.startswith(location):
                # Get relative path
                astroDir = os.path.relpath(subfolder, location)
                self.backupDrive_astroDir.delete(0, tk.END)
                self.backupDrive_astroDir.insert(0, astroDir)
            elif subfolder:
                messagebox.showerror("Error", "Selected folder is not inside the Location folder.")

    def get_selected_dwarf_id(self):
        selected_name = self.backupDrive_dwarf_var.get()
        return self.dwarf_name_to_id.get(selected_name)

    def save_or_update_backup_drive(self):
        name = self.backupDrive_name.get()
        desc = self.backupDrive_desc.get()
        location = self.backupDrive_location.get()
        astroDir = self.backupDrive_astroDir.get()
        dwarf_id = self.get_selected_dwarf_id()

        if not (name and location and dwarf_id):
            messagebox.showerror("Error", "Fill all fields and save a Dwarf first.")
            return

        existing = get_backupDrive_id_from_location(self.conn, location)

        if existing:
            # Ask user for confirmation before updating
            confirm = messagebox.askyesno("Confirm Update", "This location already exists. Do you want to update its data?")
            if confirm:
                set_backupDrive_detail(self.conn,name, desc, astroDir, dwarf_id, location)
                self.refresh_backupDrive_list()
                messagebox.showinfo("Updated", "BackupDrive info updated.")
        else:
            try:
                add_backupDrive_detail(self.conn, name, desc, location, astroDir, dwarf_id)
                self.refresh_backupDrive_list()
                messagebox.showinfo("Saved", "Backup drive saved.")
            except sqlite3.IntegrityError:
                messagebox.showerror("Error", "This folder is already registered.")

    def save_backup_drive(self):
        name = self.backupDrive_name.get()
        desc = self.backupDrive_desc.get()
        location = self.backupDrive_location.get()
        astroDir = self.backupDrive_astroDir.get()
        dwarf_id = self.get_selected_dwarf_id()

        if not (name and location and dwarf_id):
            messagebox.showerror("Error", "Fill all fields and save a Dwarf first.")
            return

        cursor = self.conn.cursor()
        try:
            add_backupDrive_detail(self.conn, name, desc, location, astroDir, dwarf_id)
            self.refresh_backupDrive_list()
            messagebox.showinfo("Saved", "Backup drive saved.")
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "This folder is already registered.")

    def update_backup_drive(self):
        location = self.backupDrive_location.get()
        name = self.backupDrive_name.get()
        desc = self.backupDrive_desc.get()
        astroDir = self.backupDrive_astroDir.get()
        dwarf_id = self.get_selected_dwarf_id()

        if not location:
            messagebox.showwarning("Warning", "No location selected.")
            return

        existing = get_backupDrive_id_from_location(self.conn, location)
        if not existing:
            messagebox.showinfo("Not Found", "No BackupDrive registered at this location.")
            return

        set_backupDrive_detail(self.conn, name, desc, astroDir, dwarf_id, location)
        self.refresh_backupDrive_list()
        messagebox.showinfo("Updated", "BackupDrive info updated.")

    def analyze_usb_drive(self):
        if not self.dwarf_id:
            messagebox.showwarning("Warning", "No Dwarf selected.")
            return

        dwarf_location = self.dwarf_astroDir.get().strip()
        if not dwarf_location: 
            messagebox.showwarning("Warning", "No Usb location selected.")
            return

        try:
            close_db(self.conn)
            print(f"🔍 Scanning: {dwarf_location}")
            total, deleted = scan_backup_folder(self.database, dwarf_location, None, self.dwarf_id, None)
            if deleted and deleted > 1:
                messagebox.showinfo("Analysis Complete", f"{total} new files found, {deleted} files are s not more present.")
            elif deleted == 1:
                messagebox.showinfo("Analysis Complete", f"{total} new files found, {deleted} file is not more present.")
            else:
                messagebox.showinfo("Analysis Complete", f"{total} new files found.")

            self.conn = connect_db(self.database)
            ExploreApp(tk.Toplevel(self.master), self.conn, None, None)

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def analyze_drive(self):
        location = self.backupDrive_location.get()
        if not location:
            messagebox.showwarning("Warning", "No location selected.")
            return
        try:
            astroDir = self.backupDrive_astroDir.get()
            backup_drive_id, dwarf_id = insert_or_get_backup_drive(self.conn, location)

            close_db(self.conn)
            print(f"🔍 Scanning: {location}-{astroDir}")
            total, deleted = scan_backup_folder(self.database, location, astroDir, dwarf_id, backup_drive_id)
            if deleted > 1:
                messagebox.showinfo("Analysis Complete", f"{total} new files found, {deleted} files are s not more present.")
            elif deleted == 1:
                messagebox.showinfo("Analysis Complete", f"{total} new files found, {deleted} file is not more present.")
            else:
                messagebox.showinfo("Analysis Complete", f"{total} new files found.")

            self.conn = connect_db(self.database)
            ExploreApp(tk.Toplevel(self.master), self.conn, backup_drive_id)

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def confirm_and_delete_BackupDrive(self):
        if self.backupDrive_id is None:
            messagebox.showerror("Error", "No Backup Drive selected.")
            return

        if has_related_backup_entries(self.conn, self.backupDrive_id):
            messagebox.showwarning(
                "Cannot Delete",
                "This Backup Drive is still in use by one or more backup entries. Please remove them first."
            )
            return

        confirm = messagebox.askyesno(
            "Confirm Deletion",
            "Are you sure you want to delete this Backup Drive?"
        )
        if confirm:
            # Delete the BackupDrive
            del_backupDrive(self.conn, self.backupDrive_id)

            self.refresh_backupDrive_list()
            self.set_new_BackupDrive()
            print(f"Deleted BackupDrive {self.backupDrive_id}.")
            messagebox.showinfo("Deleted", "BackupDrive deleted.")

    def confirm_and_delete_entries(self):
        if self.backupDrive_id is None:
            messagebox.showerror("Error", "No Backup Drive selected.")
            return

        confirm = messagebox.askyesno(
            "Confirm Deletion",
            "This will delete all backup entries and associated DwarfData for the selected BackupDrive.\nAre you sure?"
        )
        if confirm:
            delete_backup_entries_and_dwarf_data(self.conn, self.backupDrive_id)
            messagebox.showinfo("Done", "Backup entries and DwarfData deleted.")

    def confirm_and_delete_dwarf_entries(self):
        if self.dwarf_id is None:
            messagebox.showerror("Error", "No Dwarf selected.")
            return

        confirm = messagebox.askyesno(
            "Confirm Deletion",
            "This will delete all database DwarfData entries for the selected Dwarf.\nAre you sure?\n"
            "This will not delete any data on the Dwarf"
        )
        if confirm:
            delete_dwarf_entries_and_dwarf_data(self.conn, self.dwarf_id)
            messagebox.showinfo("Done", "DwarfData database entries deleted.")

    def show_data(self):
        try:
            ExploreApp(tk.Toplevel(self.master), self.conn)

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def show_dwarf_data(self):
        try:
            ExploreApp(tk.Toplevel(self.master), self.conn, None, None)

        except Exception as e:
            messagebox.showerror("Error", str(e))
