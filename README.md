# dwarfium-scope-archive
A tool to explore your Dwarf Session


Installation

1. Clone this repository 

2. Then Installdependancies  with
  
     python -m pip install -r requirements.txt


Then you can start it with => python .\dwarf_backup_cli.py --gui

You can use python .\dwarf_backup_cli.py to see your achives files associate with the target in the database

the database is a sqlite3, it will be created at startup, the name is dwarf_backup.db

You can analyse your sessions saved on Hard Disk or your current session on the Dwarf connected with USB.

# Dwarfium Scope Archive

Welcome to the Dwarfium Scope Archive project! 
This project is designed to manage and organize astrophotography data from the DWARF telescope system.
It includes tools for handling backups, organizing images, and integrating various devices like USB, FTP, and MTP (DWARF2) for seamless data transfer. 

## Table of Contents

- [Introduction](#chapter-1-introduction)
- [Installation](#chapter-2-installation)
- [Usage](#chapter-3-usage)
- [Features](#chapter-4-features)
- [Upcoming Features](#chapter-5-upcoming-features)
- [Contributing](#chapter-6-contributing)
- [License](#chapter-7-license)

## Chapter 1: Introduction

The Dwarfium Scope Archive is a collection of pages designed to manage backups and organize astrophotography files produced by the Dwarfium telescope. This includes managing FITS files, JPG images, and other related metadata for easy retrieval and processing.

This project is currently under active development, and some features (such as FTP and MTP integrations) are yet to be fully implemented.

## Chapter 2: Installation

To install the Dwarfium Scope Archive, follow these steps:

### Prerequisites

- Python 3.10+

### Setting Up a Virtual Environment

We recommend using a virtual environment to manage dependencies cleanly.
  ```bash
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`

  ```

### Installation Steps
Clone the repository:

  ```bash
git clone https://github.com/yourusername/dwarfium-scope-archive.git
  ```
  
Install the necessary Python libraries:

  ```bash
pip install -r requirements.txt
  ```

Install the necessary Python libraries on windows:

  ```bash
pip install -r requirements-windows.txt
  ```

Currently Supported Devices: USB, FTP, and MTP but only to Archive the files.

## Chapter 3: Usage

Running the Application
To launch the application, run:

  ```bash
python dwarfium_scope_archive.py
  ```

or use the build DwarfiumScopeArchivebuild.exe directly on windows

## Chapter 4: Features

### Home Page:

On this page, you will see a slideshow of your favorite images, which you have marked on the Explore Page.

![image](https://github.com/user-attachments/assets/8d4f60fe-27a2-462e-a834-7c98972c011a)

### Dwarf Configuration Page:

Configure your Dwarf device by adding a name, a description, and the USB path when it's plugged into your computer. You can also provide the IP address in STA Mode to connect with FTP.

![image](https://github.com/user-attachments/assets/58704632-0e47-4f06-ba20-37278b679dbe)

For Dwarf 2, it will be detected on your computer through MTP. This will allow you to scan its drive and later add sessions to your backup drive.

Two action buttons allow you to:

Launch a scan of the Dwarf drive.

Launch the Explore path to view what's currently on your Dwarf, including:

Image previews.

Session details (exposure, gain, number of images).

Whether the session is backed up or not.

You can then directly backedup with the Backup button

![explore backeup](https://github.com/user-attachments/assets/e097e8f0-8b3e-4377-a9b5-87d018019524)


### Backup Page:

Configure your Backup Drive by adding a name, description, and the main path of the backup drive. Specify a subdirectory within the backup drive where you want to store your Dwarf sessions.

![image](https://github.com/user-attachments/assets/2c73c433-e4fb-40d2-887e-bb748ebe40ef)

A backup drive is associated with a Dwarf device.

You can create multiple levels of directories. For example, you could create a sublevel with object names, and under each object, store its sessions. This way, all your sessions will be organized by object name (directory name) instead of the target present in the session.

A catalog is now included, Go to the Catalog page to manage your object list, allowing you to change the object of a session.

Launch the Explore path to view what's currently on your Backup (see next session for more details), including:

Image previews.

Session details (exposure, gain, number of images).

Whether the session is stored on the Dwarf or not, or if you have multiple versions of the same session..

You can also directly restore it with the Restore button

<img width="1651" height="1007" alt="image" src="https://github.com/user-attachments/assets/969eeb0c-51ab-4bdf-b566-da5b949c5588" />

Additionally, there will be a section to add Darks sessions, which you can associate with your sessions for processing.

### Explore Page:
This is the main view where you can see your sessions, organized by object, backup, or Dwarf.

<img width="525" height="812" alt="image" src="https://github.com/user-attachments/assets/eb3858c6-a241-4418-b27f-d900134a5543" />

You will be able to:

View images (JPG, PNG, or even FITS).

Add images to your favorites.

Open images in full screen.

Open the image's directory.

You will also have access to all the session details, such as the number of images, exposure, gain, and more.
You'll also know if the session is stored on your Dwarf or not.

You can update the target name by matching the coordinates with nearby objects from the catalog

click on Identify Target button

<img width="810" height="330" alt="image" src="https://github.com/user-attachments/assets/d760ea70-1e80-430a-b963-950daa5afaae" />

Select the target you prefer and click the corresponding button on the right.
You can also edit the description to suit your needs.

If you have trouble finding the correct target, you can open the Aladin view, which will display a sky map centered on the coordinates of your session target.

<img width="417" height="231" alt="image" src="https://github.com/user-attachments/assets/8497283d-7cd5-4896-b270-5a6e760d6c4c" />

In this way, your session will be classified under this name, and you can group different sessions of the same target, even if they were not originally linked. The initial target will be displayed in brackets [ ].

If you have taken a Mosaic you will have access to the different panels.

![mosaic](https://github.com/user-attachments/assets/2e83d8a8-8a1a-432d-85f0-2f13997d1159)

![pannels](https://github.com/user-attachments/assets/8ee96ed0-018f-41bd-898c-803b9afcea91)

You can also archive, restore, or even delete the session using the corresponding buttons, which will take you to the appropriate page
<img width="678" height="84" alt="image" src="https://github.com/user-attachments/assets/f7faa726-659a-4bdd-a6fc-5e3025b23a66" />

### Catalog Page
In this page, you can associate a target detecting during the scan process to an object of the build in DSO Catalog from Dwarfium

![catalog](https://github.com/user-attachments/assets/b566b572-6575-4741-aeb1-dad76df3cd02)

Click on ASSIGN / CHANGE button on the right of the desired line 

In the dialog you can type in the search input, the Select Dso list will be filled with the corresponding values
![dialog box](https://github.com/user-attachments/assets/bccb4c1a-62ba-4da3-b082-a015bf7c6557)

Then if you want you can edit the description as you want. 

### Chapter 5: Features implemented but need more test

FTP Support:
Integration with FTP, allowing direct connection to the Dwarf for data retrieval and storage.

MTP Support:
Integration with MTP (Media Transfer Protocol) for Dwarf 2 to analyze the current Dwarf disk.

### Chapter 5: Upcoming Features

FITS Updates:
Enhancements and updates to better handle FITS files, including new features and improved processing.

Moving Files Between Backup / Object:
Feature to move files between different backups or object directories, enabling better organization.

Add Darks Backup and Association with Dwarf:
Support for managing Darks sessions, including adding and associating them with Dwarf sessions for processing.

### Chapter 6: Contributing

We welcome contributions to the Dwarfium Scope Archive! Here’s how you can contribute:

Fork the repository

Create a new branch

Make your changes

Submit a pull request

For bug reports or feature requests, please open an issue.

### Chapter 7: License

This project is licensed under the MIT License

