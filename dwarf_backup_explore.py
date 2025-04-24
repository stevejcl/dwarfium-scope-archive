import os
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from astropy.io import fits
from datetime import datetime
from dwarf_backup_fct import get_Backup_fullpath, open_folder
from dwarf_backup_db_api import get_dwarf_Names, get_Objects_dwarf, get_countObjects_dwarf, get_ObjectSelect_dwarf
from dwarf_backup_db_api import get_backupDrive_Names, get_backupDrive_dwarfId, get_backupDrive_dwarfNames, get_Objects_backup, get_countObjects_backup, get_ObjectSelect_backup
from dwarf_backup_db_api import get_session_present_in_Dwarf, get_session_present_in_backupDrive

class ExploreApp:
    def __init__(self, master, conn, BackupDriveId = None, mode="backup"):
        self.master = master
        self.conn = conn
        self.master.title("Dwarf Backup Viewer")
        self.BackupDriveId = BackupDriveId
        self.mode = mode

        # Layout
        left_frame = tk.Frame(master)
        left_frame.pack(side="left", fill="y", padx=10, pady=10)

        right_frame = tk.Frame(master)
        right_frame.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        if self.mode == "backup":
            # Backup Drive Filter
            tk.Label(left_frame, text="Backup Drive:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
            self.backup_filter_var = tk.StringVar()
            self.backup_filter_combobox = ttk.Combobox(left_frame, textvariable=self.backup_filter_var, state="readonly", width=15)
            self.backup_filter_combobox.grid(row=1, column=0, padx=0, pady=5)
            self.backup_filter_combobox.bind("<<ComboboxSelected>>", lambda e: self.load_objects())
            self.populate_backup_filter()

        else:
            self.BackupDriveId = None 

        # Dwarf Filter
        if self.mode == "backup":
           dwarf_column=1
           dwarf_combo_row=1
           dwarf_check_row=2
           dwarf_global_count_label_row=3
           dwarf_listbox_row = 4
        else:
           dwarf_column=0
           dwarf_combo_row=0
           dwarf_check_row=1
           dwarf_global_count_label_row=2
           dwarf_listbox_row = 3

        tk.Label(left_frame, text="Dwarf:").grid(row=0, column=dwarf_column, sticky="w", padx=5, pady=5)
        self.dwarf_filter_var = tk.StringVar()
        self.dwarf_filter_combobox = ttk.Combobox(left_frame, textvariable=self.dwarf_filter_var, state="readonly", width=15)
        self.dwarf_filter_combobox.grid(row=dwarf_combo_row, column=1, padx=0, pady=5)
        self.dwarf_filter_combobox.bind("<<ComboboxSelected>>", lambda e: self.load_objects())
        self.populate_dwarf_filter()

        if self.mode == "backup":
            # Checkbox: Show sessions only on selected Dwarf
            self.only_on_dwarf_var = tk.BooleanVar()
            self.only_on_dwarf_check = tk.Checkbutton(
                left_frame,
                text="Only show sessions on selected Dwarf",
                variable=self.only_on_dwarf_var,
                command=self.load_objects
            )
            self.only_on_dwarf_check.grid(row=dwarf_check_row, columnspan=2, pady=5)
        else:
            # Checkbox: Show sessions only on selected Dwarf
            self.only_on_backup_var = tk.BooleanVar()
            self.only_on_backup_check = tk.Checkbutton(
                left_frame,
                text="Only show backed up sessions of selected Dwarf",
                variable=self.only_on_backup_var,
                command=self.load_objects
            )
            self.only_on_backup_check.grid(row=dwarf_check_row, columnspan=2, pady=5)

        self.global_count_label = tk.Label(left_frame, text="Total matching sessions: 0")
        self.global_count_label.grid(row=dwarf_global_count_label_row, columnspan=2, pady=5)

        self.object_listbox = tk.Listbox(left_frame, width=40, height=50)
        self.object_listbox.grid(row=dwarf_listbox_row, columnspan=2, pady=5)

        # Combobox to select individual files
        self.file_combobox = ttk.Combobox(right_frame, width=100, state="readonly")
        self.file_combobox.grid(row=0, column=0, padx=(0, 10), pady=5, sticky="ew")

        # Button (right side)
        open_button = tk.Button(right_frame, text="🗁 Open", command=lambda: open_folder(self.selected_path_var))
        open_button.grid(row=0, column=1, pady=5, sticky="e")

        # Row 1: Details Text (spanning both columns)
        self.details_text = tk.Text(right_frame, width=150, height=4)
        self.details_text.grid(row=1, column=0, columnspan=2, pady=5, sticky="ew")
        self.details_text.tag_configure("green", foreground="green")

        # Row 2: Image Label (spanning both columns)
        self.image_label = tk.Label(right_frame)
        self.image_label.grid(row=2, column=0, columnspan=2, sticky="nsew")

        # Allow column 0 to expand
        right_frame.columnconfigure(0, weight=1)
        # Optionally: column 1 (button) doesn't need to expand

        # Allow row 2 (image) to expand vertically
        right_frame.rowconfigure(2, weight=1)

        # Store current selected path
        self.selected_path_var = tk.StringVar()

        self.run()

    def populate_backup_filter(self):
        self.backup_options = get_backupDrive_Names(self.conn)

        display_values = ["(All Backups)"] + [name for _, name in self.backup_options]
        self.backup_filter_combobox["values"] = display_values

        # Set current selection to match self.BackupDriveId if set
        if self.BackupDriveId:
            try:
                index = [id_ for id_, _ in self.backup_options].index(self.BackupDriveId)
                self.backup_filter_combobox.current(index + 1)
            except ValueError:
                self.backup_filter_combobox.current(0)
        else:
            self.backup_filter_combobox.current(0)

        # Bind selection change
        self.backup_filter_combobox.bind("<<ComboboxSelected>>", self.on_backup_filter_change)

    def on_backup_filter_change(self, event=None):
        selected_name = self.backup_filter_var.get()
        if selected_name == "(All Backups)":
            self.BackupDriveId = None
            self.populate_dwarf_filter()
        else:
            for bid, name in self.backup_options:
                if name == selected_name:
                    self.BackupDriveId = bid
                    break
            self.populate_dwarf_filter(self.BackupDriveId)

        self.load_objects()

    def populate_dwarf_filter(self, backup_drive_id=None):

        if backup_drive_id:
            # Get the dwarf_id for the given BackupDrive
            current_dwarf_id = get_backupDrive_dwarfId(self.conn, backup_drive_id)
            # Fetch dwarfs linked to this backup
            self.dwarf_options =  get_backupDrive_dwarfNames(self.conn, backup_drive_id)
            show_all = False
        else:
            current_dwarf_id = None
            self.dwarf_options = get_dwarf_Names(self.conn)
            show_all = True

        if show_all:
            display_values = ["(All Dwarfs)"] + [name for _, name in self.dwarf_options]
            self.dwarf_filter_combobox["values"] = display_values
            self.dwarf_filter_combobox.current(0)
        else:
            display_values = [name for _, name in self.dwarf_options]
            self.dwarf_filter_combobox["values"] = display_values

            if current_dwarf_id is not None:
                # Try to select the matching dwarf by ID
                for idx, (d_id, _) in enumerate(self.dwarf_options):
                    if d_id == current_dwarf_id:
                        self.dwarf_filter_combobox.current(idx)
                        break
            elif display_values:
                self.dwarf_filter_combobox.current(0)
            else:
                self.dwarf_filter_combobox.set("")

        self.dwarf_filter_var.trace_add("write", self.update_checkbox_state)

    def get_selected_dwarf_id(self):
        selected_index = self.dwarf_filter_combobox.current()
        if selected_index < 0:
            return None

        if self.BackupDriveId is None:
            if selected_index == 0:
                return None  # "(All Dwarfs)"
            return self.dwarf_options[selected_index - 1][0]
        else:
            return self.dwarf_options[selected_index][0]

    def update_checkbox_state(self, *args):
        if self.mode == "backup":
            selected = self.dwarf_filter_var.get()
            if selected == "(All Dwarfs)":
                self.only_on_dwarf_var.set(False)
                self.only_on_dwarf_check.config(state="disabled")
            else:
                self.only_on_dwarf_check.config(state="normal")
        else:
            selected = self.dwarf_filter_var.get()
            if selected == "(All Dwarfs)":
                self.only_on_backup_var.set(False)
                self.only_on_backup_check.config(state="disabled")
            else:
                self.only_on_backup_check.config(state="normal")

    def load_objects(self):

        dwarf_id = self.get_selected_dwarf_id()
        if self.mode == "backup":
            objects = get_Objects_backup(self.conn, self.BackupDriveId, dwarf_id, self.only_on_dwarf_var.get())

        else:
            objects = get_Objects_dwarf(self.conn, dwarf_id, self.only_on_backup_var.get())

        self.count_objects(dwarf_id)

        self.object_listbox.delete(0, tk.END)
        for oid, name in objects:
            print(f"{oid} - {name}")
            self.object_listbox.insert(tk.END, f"{oid} - {name}")

    def count_objects(self, dwarf_id):

        if self.mode == "backup":
            global_count = get_countObjects_backup(self.conn, self.BackupDriveId, dwarf_id, self.only_on_dwarf_var.get())
        else:
            global_count = get_countObjects_dwarf(self.conn, dwarf_id, self.only_on_backup_var.get())

        print(f"Global count of matching sessions: {global_count}")

        # Optional: show it in a label
        self.global_count_label.config(text=f"Total matching sessions: {global_count}")

    def get_preview_image_path(self,file_path):
        base_dir = os.path.dirname(file_path)

        for name in ["stacked.jpg", "stacked.png"]:
            candidate = os.path.join(base_dir, name)
            if os.path.exists(candidate):
                return candidate
        return None

    def load_preview_image(self,file_path, max_size=(1280, 720)):
        fallback = self.get_preview_image_path(file_path)
        if fallback:
            try:
                img = Image.open(fallback)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)  # Conserve le ratio
                return ImageTk.PhotoImage(img)
            except Exception as e:
                print(f"Error loading preview image: {e}")
                return None
        else:
            print("No preview image available.")
            return None

    def load_fits_preview(self,fits_path):
        try:
            with fits.open(fits_path) as hdul:
                data = hdul[0].data
                data = np.nan_to_num(data).squeeze()

                if data.ndim != 2:
                    raise ValueError(f"Unsupported FITS data shape: {data.shape}")

                # Normalize to 8-bit
                norm_data = cv2.normalize(data, None, 0, 255, cv2.NORM_MINMAX)
                norm_data = norm_data.astype(np.uint8)

                # Debayer assuming RGGB (you may need to test BG, GR, GB depending on your camera)
                rgb_image = cv2.cvtColor(norm_data, cv2.COLOR_BAYER_RG2RGB)

                # Resize to display size
                rgb_image = cv2.resize(rgb_image, (400, 400), interpolation=cv2.INTER_AREA)

                # Convert to PIL for Tkinter display
                img = Image.fromarray(rgb_image)
                return ImageTk.PhotoImage(img)

        except Exception as e:
            print(f"Error loading FITS: {e}")
            return None

    def show_date_session(self,date_db):
        dt = datetime.strptime(date_db, "%Y-%m-%d %H:%M:%S.%f")
        date_session = dt.strftime("%B %d, %Y at %I:%M:%S %p")
        return date_session

    def on_object_select(self,event):
        selection = self.object_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        line = self.object_listbox.get(index)
        object_id = int(line.split(" - ")[0])

        dwarf_id = self.get_selected_dwarf_id()

        if self.mode == "backup":
            files = get_ObjectSelect_backup(self.conn, object_id, self.BackupDriveId, dwarf_id, self.only_on_dwarf_var.get()) 
        else:
            files = get_ObjectSelect_dwarf(self.conn, object_id, dwarf_id, self.only_on_backup_var.get()) 

        # Store all rows globally so we can access them later
        self.file_combobox.file_rows = files

        if len(files) == 1:
            # Si un seul fichier, le mettre dans le ComboBox et l'afficher directement
            file_path = files[0][1]
            backup_path = files[0][6]  # location from BackupDrive or USB Dwarf

            full_path = get_Backup_fullpath (backup_path, "", file_path)

            self.file_combobox['values'] = [f"{files[0][1]}"]
            self.file_combobox.set(self.file_combobox['values'][0])  # Set the default value to the single file
            self.details_text.delete("1.0", tk.END)
            self.details_text.insert(tk.END, f"File: {full_path}\n\n")
            self.details_text.insert(tk.END, f"Taken on {files[0][9]} | {self.show_date_session(files[0][7])} | Exposure: {files[0][2]}s | Gain: {files[0][3]} | Filter: {files[0][4]} | Stacks: {files[0][5]}\n")

            if self.mode == "backup":
                result_on_Dwarf = get_session_present_in_Dwarf(self.conn,files[0][8])
                if result_on_Dwarf:
                    self.details_text.insert(tk.END, f"Actually available on {result_on_Dwarf[1]}\n", "green")

            else:
                result_on_backupDrive = get_session_present_in_backupDrive(self.conn,files[0][8])
                if result_on_backupDrive:
                    backup_full_path = get_Backup_fullpath (result_on_backupDrive[2], result_on_backupDrive[3], files[0][1])
                    self.details_text.insert(tk.END, f"Actually available on {backup_full_path}\n", "green")

            # Charger et afficher l'image automatiquement
            preview = self.load_preview_image(full_path)
            if preview:
                self.image_label.config(image=preview, text="")
                self.image_label.image = preview
            else:
                self.image_label.config(image='', text="No preview available")

            self.selected_path_var.set(os.path.dirname(full_path))
        else:
            # Populate combobox with readable file names
            self.selected_path_var.set("")
            self.file_combobox['values'] = [f"{row[1]} (Taken on {row[9]} | {self.show_date_session(row[7])}, exp {row[2]}s, gain {row[3]}, filter {row[4]}, stacks {row[5]})" for row in files]
            self.file_combobox.set("Sélectionnez un fichier...")

            self.details_text.delete("1.0", tk.END)
            self.details_text.insert(tk.END, f"{len(files)} fichier(s) disponible(s) pour cet objet.\n")
            self.image_label.config(image='')
            self.image_label.image = None

    def on_file_selected(self,event):
        selection_index = self.file_combobox.current()
        if selection_index == -1:
            return

        row = self.file_combobox.file_rows[selection_index]
        file_path, exp, gain, ircut, stacks, backup_path, date_session, dir_session, dwarf = row[1:]

        full_path = get_Backup_fullpath (backup_path, "", file_path)
        self.details_text.delete("1.0", tk.END)
        self.details_text.insert(tk.END, f"File: {full_path}\n\n")
        self.details_text.insert(tk.END, f"Taken on {dwarf} | Date: {self.show_date_session(date_session)} |  Exposure: {exp}s | Gain: {gain} | Filter: {ircut} | Stacks: {stacks}\n")

        if self.mode == "backup":
            result_on_Dwarf = get_session_present_in_Dwarf(self.conn,dir_session)
            if result_on_Dwarf:
                self.details_text.insert(tk.END, f"Actually available on {result_on_Dwarf[1]}\n", "green")
        else:
            result_on_backupDrive = get_session_present_in_backupDrive(self.conn,dir_session)
            if result_on_backupDrive:
                backup_full_path = get_Backup_fullpath (result_on_backupDrive[2], result_on_backupDrive[3], file_path)
                self.details_text.insert(tk.END, f"Actually available on {backup_full_path}\n", "green")

        preview = self.load_preview_image(full_path)
        if preview:
            self.image_label.config(image=preview, text="")
            self.image_label.image = preview
        else:
            self.image_label.config(image='', text="No preview available")

        self.selected_path_var.set(os.path.dirname(full_path))

    def run(self):
        self.object_listbox.bind("<<ListboxSelect>>", self.on_object_select)
        self.file_combobox.bind("<<ComboboxSelected>>", self.on_file_selected)

        self.load_objects()

